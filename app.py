import os
from functools import wraps
from io import BytesIO
from datetime import datetime
from urllib.parse import quote
import unicodedata
import re

from flask import Flask, render_template, redirect, url_for, request, flash, abort, send_from_directory, make_response
from flask_login import (
    LoginManager, login_user, logout_user, login_required, current_user
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from xhtml2pdf import pisa

from models import db, User, Education, Experience, Certificate, Project, Department

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
TRANSCRIPT_FOLDER = os.path.join(BASE_DIR, "uploads", "transcripts")
PHOTO_FOLDER = os.path.join(BASE_DIR, "uploads", "photos")

ALLOWED_TRANSCRIPT_EXTENSIONS = {"pdf", "jpg", "jpeg", "png"}
ALLOWED_PHOTO_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-anahtari-degistir")
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(BASE_DIR, "cv_platform.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["UPLOAD_FOLDER"] = TRANSCRIPT_FOLDER
app.config["PHOTO_FOLDER"] = PHOTO_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10 MB

db.init_app(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "index"


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_TRANSCRIPT_EXTENSIONS


def allowed_photo(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_PHOTO_EXTENSIONS


def role_required(role):
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated or current_user.role != role:
                abort(403)
            return f(*args, **kwargs)
        return wrapped
    return decorator


def parse_dynamic_rows(prefix, fields, required_field):
    lists = {f: request.form.getlist(f"{prefix}_{f}[]") for f in fields}
    length = max((len(v) for v in lists.values()), default=0)
    rows = []
    for i in range(length):
        row = {f: (lists[f][i].strip() if i < len(lists[f]) else "") for f in fields}
        if row.get(required_field):
            rows.append(row)
    return rows


def seed_departments():
    """Tabloda bölüm yoksa ilk açılışta deneme bölümlerini yükler."""
    initial_departments = [
        "Fiber Teknolojisi",
        "Kurumsal Bilişim"
    ]
    for dept_name in initial_departments:
        if not Department.query.filter_by(name=dept_name).first():
            db.session.add(Department(name=dept_name))
    db.session.commit()


# ---------- Genel sayfalar ve Medya ----------

@app.context_processor
def inject_globals():
    """Her sablonda kullanilabilen degerler (footer telif yili gibi)."""
    return {"now_year": datetime.now().year}


# ---------- Hata sayfalari ----------
# Varsayilan Flask sayfalari stilsiz geliyor; tasarim sistemiyle ayni
# kabukta gosterilsinler diye tek bir sablona baglandilar.

def _error_page(code, title, text):
    return render_template("error.html", code=code, title=title, text=text), code


@app.errorhandler(403)
def error_forbidden(e):
    return _error_page(
        403, "Bu sayfaya erişiminiz yok",
        "Bu bölüm başka bir hesap türü için. Öğrenci hesabıyla kurum sayfalarına "
        "(veya tersi) girilemez.",
    )


@app.errorhandler(404)
def error_not_found(e):
    return _error_page(
        404, "Sayfa bulunamadı",
        "Aradığınız adres değişmiş ya da hiç var olmamış olabilir.",
    )


@app.errorhandler(413)
def error_too_large(e):
    return _error_page(
        413, "Dosya çok büyük",
        "Yüklediğiniz dosya 10 MB sınırını aşıyor. Daha küçük bir dosya seçip "
        "tekrar deneyin.",
    )


@app.errorhandler(500)
def error_server(e):
    return _error_page(
        500, "Bir şeyler ters gitti",
        "Sunucuda beklenmedik bir hata oluştu. Lütfen biraz sonra tekrar deneyin.",
    )


@app.route("/kvkk")
def kvkk():
    return render_template("kvkk.html")


@app.route("/")
def index():
    if current_user.is_authenticated:
        if current_user.role == "student":
            return redirect(url_for("student_dashboard"))
        return redirect(url_for("company_dashboard"))
    return render_template("index.html")


@app.route("/uploads/photos/<filename>")
def uploaded_photo(filename):
    return send_from_directory(app.config["PHOTO_FOLDER"], filename)


# ---------- Öğrenci: kayıt / giriş ----------

@app.route("/student/register", methods=["GET", "POST"])
def student_register():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        full_name = request.form.get("full_name", "").strip()

        if not email or not password or not full_name:
            flash("Lütfen tüm alanları doldurun.", "error")
            return redirect(url_for("student_register"))

        if User.query.filter_by(email=email).first():
            flash("Bu e-posta ile zaten bir hesap var.", "error")
            return redirect(url_for("student_register"))

        user = User(
            email=email,
            password_hash=generate_password_hash(password),
            role="student",
            full_name=full_name,
            is_approved=True  # Öğrenci doğrudan aktif
        )
        db.session.add(user)
        db.session.commit()
        login_user(user)
        flash("Kayıt başarılı, şimdi özgeçmiş bilgilerinizi girebilirsiniz.", "success")
        return redirect(url_for("student_cv_form"))

    return render_template("student_register.html")


@app.route("/student/login", methods=["GET", "POST"])
def student_login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=email, role="student").first()

        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for("student_dashboard"))

        flash("E-posta veya şifre hatalı.", "error")
        return redirect(url_for("student_login"))

    return render_template("student_login.html")


# ---------- Öğrenci: dashboard / CV formu ----------

@app.route("/student/dashboard")
@login_required
@role_required("student")
def student_dashboard():
    return render_template("student_dashboard.html", student=current_user)


@app.route("/student/cv", methods=["GET", "POST"])
@login_required
@role_required("student")
def student_cv_form():
    departments = Department.query.order_by(Department.name).all()

    if request.method == "POST":
        current_user.full_name = request.form.get("full_name", "").strip()
        current_user.department = request.form.get("department", "").strip()
        current_user.phone = request.form.get("phone", "").strip()
        current_user.summary = request.form.get("summary", "").strip()
        current_user.skills = request.form.get("skills", "").strip()

        # Profil Fotoğrafı Yükleme
        photo = request.files.get("photo")
        if photo and photo.filename:
            if not allowed_photo(photo.filename):
                flash("Fotoğraf için sadece JPG, PNG veya WEBP yükleyebilirsiniz.", "error")
                return redirect(url_for("student_cv_form"))
            ext = photo.filename.rsplit(".", 1)[1].lower()
            photo_filename = secure_filename(f"photo_{current_user.id}_{int(datetime.utcnow().timestamp())}.{ext}")
            photo.save(os.path.join(app.config["PHOTO_FOLDER"], photo_filename))
            current_user.photo_filename = photo_filename

        # Transkript yükleme
        file = request.files.get("transcript")
        if file and file.filename:
            if not allowed_file(file.filename):
                flash("Sadece PDF, JPG veya PNG dosyası yükleyebilirsiniz.", "error")
                return redirect(url_for("student_cv_form"))
            ext = file.filename.rsplit(".", 1)[1].lower()
            filename = secure_filename(f"transcript_{current_user.id}.{ext}")
            file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
            current_user.transcript_filename = filename

        # Dinamik bölümleri sıfırlayıp yeniden oluştur
        Education.query.filter_by(student_id=current_user.id).delete()
        Experience.query.filter_by(student_id=current_user.id).delete()
        Certificate.query.filter_by(student_id=current_user.id).delete()
        Project.query.filter_by(student_id=current_user.id).delete()

        for row in parse_dynamic_rows(
            "edu", ["degree_type", "school", "department", "gpa", "start_year", "end_year"], "school"
        ):
            db.session.add(Education(student_id=current_user.id, **row))
            
        for row in parse_dynamic_rows(
            "exp", ["company", "position", "start_date", "end_date", "description"], "company"
        ):
            db.session.add(Experience(student_id=current_user.id, **row))

        for row in parse_dynamic_rows(
            "cert", ["name", "institution", "date"], "name"
        ):
            db.session.add(Certificate(student_id=current_user.id, **row))

        for row in parse_dynamic_rows(
            "proj", ["title", "description", "tech_stack", "link"], "title"
        ):
            db.session.add(Project(student_id=current_user.id, **row))

        db.session.commit()
        flash("Özgeçmişiniz güncellendi.", "success")
        return redirect(url_for("student_dashboard"))

    return render_template("student_cv_form.html", student=current_user, departments=departments)


@app.route("/student/preview")
@login_required
@role_required("student")
def student_preview():
    return render_template("cv_detail.html", student=current_user, is_own_preview=True)


# ---------- Kurum: kayıt / giriş ----------

@app.route("/company/register", methods=["GET", "POST"])
def company_register():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        company_name = request.form.get("company_name", "").strip()
        contact_person = request.form.get("contact_person", "").strip()

        if not email or not password or not company_name:
            flash("Lütfen tüm alanları doldurun.", "error")
            return redirect(url_for("company_register"))

        if User.query.filter_by(email=email).first():
            flash("Bu e-posta ile zaten bir hesap var.", "error")
            return redirect(url_for("company_register"))

        user = User(
            email=email,
            password_hash=generate_password_hash(password),
            role="company",
            company_name=company_name,
            contact_person=contact_person,
            is_approved=False  # <-- Yönetici onayı bekleyecek
        )
        db.session.add(user)
        db.session.commit()
        
        flash("Kurum kaydınız alındı. Kariyer Merkezi/Yönetici onayından sonra aday havuzuna erişebilirsiniz.", "info")
        return redirect(url_for("company_login"))

    return render_template("company_register.html")

@app.route("/company/login", methods=["GET", "POST"])
def company_login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=email, role="company").first()

        if user and check_password_hash(user.password_hash, password):
            if not user.is_approved:
                flash("Hesabınız henüz onaylanmadı. Kampüs koordinatörünün onayını bekleyiniz.", "error")
                return redirect(url_for("company_login"))

            login_user(user)
            return redirect(url_for("company_dashboard"))

        flash("E-posta veya şifre hatalı.", "error")
        return redirect(url_for("company_login"))

    return render_template("company_login.html")


# ---------- Kurum: aday havuzu & İndirme ----------

# Aday havuzunda sıralanabilir kolonlar.
# Her kolon için iki fonksiyon: (sıralama değeri, değer eksik mi?)
# Ortalama ve doluluk yüzdesi SQL'de değil Python'da hesaplanıyor (biri metin
# alanından parse ediliyor, diğeri ilişkilere bakan bir metot), bu yüzden
# sıralamanın tamamı Python tarafında yapılır.
CANDIDATE_SORTERS = {
    "name":        (lambda s: (s.full_name or "").casefold(), lambda s: not (s.full_name or "").strip()),
    "department":  (lambda s: (s.department or "").casefold(), lambda s: not (s.department or "").strip()),
    "gpa":         (lambda s: s.gpa_value or 0.0, lambda s: s.gpa_value is None),
    "experience":  (lambda s: len(s.experiences), lambda s: False),
    "project":     (lambda s: len(s.projects), lambda s: False),
    "certificate": (lambda s: len(s.certificates), lambda s: False),
    "transcript":  (lambda s: bool(s.transcript_filename), lambda s: False),
    "completion":  (lambda s: s.profile_completion(), lambda s: False),
    "created":     (lambda s: s.created_at or datetime.min, lambda s: s.created_at is None),
}

# Aday havuzunda sayfa basina kayit sayisi
CANDIDATES_PER_PAGE = 25


@app.route("/company/dashboard")
@login_required
@role_required("company")
def company_dashboard():
    selected_department = request.args.get("department", "")
    q = request.args.get("q", "").strip()
    only_with_transcript = request.args.get("has_transcript") == "1"

    try:
        min_completion = int(request.args.get("min_completion", 0))
    except ValueError:
        min_completion = 0

    sort = request.args.get("sort", "name")
    if sort not in CANDIDATE_SORTERS:
        sort = "name"
    direction = "desc" if request.args.get("dir") == "desc" else "asc"

    query = User.query.filter_by(role="student")
    if selected_department:
        query = query.filter_by(department=selected_department)
    if q:
        # İsim, e-posta ve yetkinliklerde birlikte ara
        like = f"%{q}%"
        query = query.filter(
            db.or_(
                User.full_name.ilike(like),
                User.email.ilike(like),
                User.skills.ilike(like),
            )
        )
    if only_with_transcript:
        query = query.filter(User.transcript_filename.isnot(None))

    students = query.all()
    total_students = User.query.filter_by(role="student").count()

    if min_completion:
        students = [s for s in students if s.profile_completion() >= min_completion]

    # İki aşamalı kararlı sıralama: önce değere göre, sonra "eksik olanlar
    # en sona" diye. Python'un sort'u kararlı olduğu için yön ne olursa olsun
    # ortalaması girilmemiş adaylar listenin sonunda kalır.
    value_of, is_missing = CANDIDATE_SORTERS[sort]
    students.sort(key=value_of, reverse=(direction == "desc"))
    students.sort(key=is_missing)

    # Sayfalama: siralama Python tarafinda yapildigi icin dilimleme de burada.
    # Istenen sayfa aralik disindaysa son sayfaya kirpilir, hata vermez.
    match_count = len(students)
    try:
        page = max(1, int(request.args.get("page", 1)))
    except ValueError:
        page = 1
    page_count = max(1, -(-match_count // CANDIDATES_PER_PAGE))
    page = min(page, page_count)
    start = (page - 1) * CANDIDATES_PER_PAGE
    students = students[start:start + CANDIDATES_PER_PAGE]

    departments = Department.query.order_by(Department.name).all()

    return render_template(
        "company_dashboard.html",
        students=students,
        departments=departments,
        selected_department=selected_department,
        q=q,
        only_with_transcript=only_with_transcript,
        min_completion=min_completion,
        sort=sort,
        direction=direction,
        total_students=total_students,
        match_count=match_count,
        page=page,
        page_count=page_count,
        range_start=start + 1 if match_count else 0,
        range_end=start + len(students),
    )


@app.route("/company/student/<int:student_id>")
@login_required
@role_required("company")
def student_detail(student_id):
    student = User.query.filter_by(id=student_id, role="student").first_or_404()
    return render_template("cv_detail.html", student=student, is_own_preview=False)


@app.route("/company/student/<int:student_id>/pdf")
@login_required
@role_required("company")
def download_student_cv_pdf(student_id):
    student = User.query.filter_by(id=student_id, role="student").first_or_404()
    
    html_content = render_template("cv_pdf.html", student=student)
    pdf_buffer = BytesIO()
    
    def link_callback(uri, rel):
        if uri.startswith("static/"):
            return os.path.join(BASE_DIR, uri)
        return os.path.join(BASE_DIR, "static", uri)

    pisa_status = pisa.CreatePDF(
        src=html_content,
        dest=pdf_buffer,
        encoding="utf-8",
        link_callback=link_callback
    )
    
    if pisa_status.err:
        flash("PDF oluşturulurken bir hata meydana geldi.", "error")
        return redirect(url_for("student_detail", student_id=student.id))
        
    pdf_data = pdf_buffer.getvalue()

    raw_name = student.full_name or "Ogrenci"
    clean_name = unicodedata.normalize("NFKD", raw_name).encode("ASCII", "ignore").decode("utf-8")
    clean_name = re.sub(r'[^a-zA-Z0-9_-]', '_', clean_name.strip())
    ascii_filename = f"CV_{clean_name or 'Ogrenci'}.pdf"
    utf8_filename = quote(f"CV_{raw_name}.pdf")
    
    response = make_response(pdf_data)
    response.headers["Content-Type"] = "application/pdf"
    response.headers["Content-Disposition"] = f"attachment; filename=\"{ascii_filename}\"; filename*=UTF-8''{utf8_filename}"
    return response


@app.route("/company/transcript/<int:student_id>")
@login_required
@role_required("company")
def download_transcript(student_id):
    student = User.query.filter_by(id=student_id, role="student").first_or_404()
    if not student.transcript_filename:
        abort(404)
    return send_from_directory(app.config["UPLOAD_FOLDER"], student.transcript_filename)


@app.route("/student/transcript")
@login_required
@role_required("student")
def download_own_transcript():
    if not current_user.transcript_filename:
        abort(404)
    return send_from_directory(app.config["UPLOAD_FOLDER"], current_user.transcript_filename)


# ---------- Çıkış ----------

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("index"))


def create_app():
    with app.app_context():
        os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
        os.makedirs(app.config["PHOTO_FOLDER"], exist_ok=True)
        db.create_all()
        seed_departments()
    return app


if __name__ == "__main__":
    create_app()
    app.run(debug=True, host="0.0.0.0", port=5000)
    
@app.cli.command("approve-company")
def approve_company():
    """Onay bekleyen kurumları listeler ve onaylama imkanı verir."""
    pending = User.query.filter_by(role="company", is_approved=False).all()
    if not pending:
        print("Onay bekleyen kurum bulunmuyor.")
        return

    print("\n--- Onay Bekleyen Kurumlar ---")
    for c in pending:
        print(f"ID: {c.id} | Şirket: {c.company_name} | Yetkili: {c.contact_person} | E-posta: {c.email}")
    
    comp_id = input("\nOnaylamak istediğiniz Kurum ID'sini girin (Tümünü onaylamak için 'all'): ").strip()
    if comp_id == "all":
        for c in pending:
            c.is_approved = True
        db.session.commit()
        print("Tüm kurumlar onaylandı.")
    elif comp_id.isdigit():
        target = User.query.get(int(comp_id))
        if target and target.role == "company":
            target.is_approved = True
            db.session.commit()
            print(f"{target.company_name} başarıyla onaylandı.")
        else:
            print("Geçersiz kurum ID.")
