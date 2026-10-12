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

from flask_migrate import Migrate

from models import db, User, Education, Experience, Certificate, Project, Department

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# Veritabani ve yuklenen dosyalar nereye yazilacak?
#
# Yerelde proje klasoru (varsayilan). Sunucuda ise kap (container) dosya
# sistemi her yeniden baslatmada sifirlandigi icin bunlarin KALICI bir
# diskte durmasi gerekir: Fly.io'da volume /data'ya baglanir ve
# DATA_DIR=/data verilir. Aksi halde her dagitimda veritabani ve
# yuklenen transkriptler silinir.
DATA_DIR = os.environ.get("DATA_DIR", BASE_DIR)

TRANSCRIPT_FOLDER = os.path.join(DATA_DIR, "uploads", "transcripts")
PHOTO_FOLDER = os.path.join(DATA_DIR, "uploads", "photos")

ALLOWED_TRANSCRIPT_EXTENSIONS = {"pdf", "jpg", "jpeg", "png"}
ALLOWED_PHOTO_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-anahtari-degistir")
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(DATA_DIR, "cv_platform.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["UPLOAD_FOLDER"] = TRANSCRIPT_FOLDER
app.config["PHOTO_FOLDER"] = PHOTO_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10 MB

db.init_app(app)

# render_as_batch: SQLite ALTER TABLE'i cok sinirli destekler (kolon silme,
# kisit degistirme yok). Alembic bu modda tabloyu gecici bir kopyaya tasiyip
# yeniden olusturur; SQLite'ta migrasyon icin pratikte zorunludur.
migrate = Migrate(app, db, render_as_batch=True)

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
        if current_user.role == "admin":
            return redirect(url_for("admin_companies"))
        return redirect(url_for("company_dashboard"))
    return render_template("index.html")


@app.route("/uploads/photos/<filename>")
@login_required
def uploaded_photo(filename):
    """Profil fotografi.

    login_required sart: dosya adi photo_<kullanici_id>_<zaman>.png
    bicimindedir, yani tahmin edilebilir. Koruma olmadan adresi bilen
    herkes ogrencilerin fotografini indirebiliyordu. Fotograf zaten
    yalnizca girisli sayfalarda gosteriliyor, bu yuzden bir sey bozulmaz.
    """
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


# ---------- Yönetici (kampüs koordinatörü) ----------
#
# Kurum hesaplari is_approved=False olarak dogar ve onaylanmadan giris
# yapamaz. Onay, bugune kadar yalnizca "flask approve-company" komutuyla
# veriliyordu; buradaki ekranlar ayni isi tarayicidan yapar.
#
# Yonetici hesabi tarayicidan ACILAMAZ: kayit sayfasi yoktur, yalnizca
# "flask create-admin" komutuyla olusturulur. Aksi halde isteyen herkes
# yonetici olup butun ogrenci verisine erisebilirdi.


@app.route("/admin/giris", methods=["GET", "POST"])
def admin_login():
    if current_user.is_authenticated and current_user.role == "admin":
        return redirect(url_for("admin_companies"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user = User.query.filter_by(email=email, role="admin").first()
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for("admin_companies"))

        flash("E-posta veya şifre hatalı.", "error")
        return redirect(url_for("admin_login"))

    return render_template("admin_login.html")


@app.route("/admin/kurumlar")
@login_required
@role_required("admin")
def admin_companies():
    companies = User.query.filter_by(role="company").order_by(User.created_at.desc()).all()
    pending = [c for c in companies if not c.is_approved]
    approved = [c for c in companies if c.is_approved]
    return render_template(
        "admin_companies.html", pending=pending, approved=approved
    )


@app.route("/admin/kurumlar/<int:company_id>/onayla", methods=["POST"])
@login_required
@role_required("admin")
def admin_approve_company(company_id):
    company = User.query.filter_by(id=company_id, role="company").first_or_404()
    company.is_approved = True
    company.approved_at = datetime.now()
    company.approved_by_id = current_user.id
    db.session.commit()
    flash(f"{company.company_name} onaylandı. Artık aday havuzuna erişebilir.", "success")
    return redirect(url_for("admin_companies"))


@app.route("/admin/kurumlar/<int:company_id>/iptal", methods=["POST"])
@login_required
@role_required("admin")
def admin_revoke_company(company_id):
    company = User.query.filter_by(id=company_id, role="company").first_or_404()
    company.is_approved = False
    # approved_at/approved_by MEVCUT onayi tarif eder; erisim kalkinca
    # temizlenir. Tam bir gecmis (her onay/iptal hareketi) istenirse ayri
    # bir tablo gerekir; bu iki kolon yalnizca son durumu tutar.
    company.approved_at = None
    company.approved_by_id = None
    db.session.commit()
    flash(f"{company.company_name} erişimi kaldırıldı.", "success")
    return redirect(url_for("admin_companies"))


@app.route("/admin/bolumler", methods=["GET", "POST"])
@login_required
@role_required("admin")
def admin_departments():
    """Bolum listesi yonetimi.

    Bolumler onceden yalnizca seed_departments() icinde sabitti; yeni bolum
    eklemek kod degisikligi gerektiriyordu. Burasi koordinatorun kendi
    ekleyip silebilmesi icin.
    """
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name:
            flash("Bölüm adı boş olamaz.", "error")
        elif Department.query.filter_by(name=name).first():
            flash(f"'{name}' zaten listede.", "error")
        else:
            db.session.add(Department(name=name))
            db.session.commit()
            flash(f"'{name}' bölümü eklendi.", "success")
        return redirect(url_for("admin_departments"))

    departments = Department.query.order_by(Department.name).all()
    # Her bolumde kac ogrenci var: silmeden once uyarmak icin
    counts = {
        d.name: User.query.filter_by(role="student", department=d.name).count()
        for d in departments
    }
    return render_template(
        "admin_departments.html", departments=departments, counts=counts
    )


@app.route("/admin/bolumler/<int:department_id>/sil", methods=["POST"])
@login_required
@role_required("admin")
def admin_delete_department(department_id):
    department = Department.query.get_or_404(department_id)

    # Bolum, ogrenci kayitlarinda metin olarak tutuluyor (iliski degil).
    # Silinirse o ogrencilerin bolumu listede olmayan bir metne doner ve
    # filtrelerde kaybolurlar; bu yuzden doluyken silinmesine izin yok.
    in_use = User.query.filter_by(role="student", department=department.name).count()
    if in_use:
        flash(
            f"'{department.name}' silinemez: {in_use} öğrenci bu bölüme kayıtlı. "
            "Önce o öğrencilerin bölümünü değiştirin.",
            "error",
        )
    else:
        db.session.delete(department)
        db.session.commit()
        flash(f"'{department.name}' bölümü silindi.", "success")

    return redirect(url_for("admin_departments"))


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
    # Debug modu disa acik bir adreste ASLA acik olmamali: hata aninda
    # tarayicida interaktif Python konsolu acilir, yani sunucuda kod
    # calistirilabilir. Yerel gelistirmede varsayilan olarak acik kalir;
    # tunel/sunucu icin FLASK_DEBUG=0 verilir.
    debug = os.environ.get("FLASK_DEBUG", "1") != "0"
    port = int(os.environ.get("PORT", 5000))

    if not debug and app.config["SECRET_KEY"] == "dev-secret-anahtari-degistir":
        raise SystemExit(
            "SECRET_KEY ayarlanmamis. Disa acik calistirmadan once ortam "
            "degiskeni olarak guclu ve rastgele bir deger verin."
        )

    app.run(debug=debug, host="0.0.0.0", port=port)
    
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


@app.cli.command("create-admin")
def create_admin():
    """Yonetici (kampus koordinatoru) hesabi olusturur.

    Yonetici hesabi tarayicidan acilamaz; tek yol bu komuttur.
    Kullanim:  flask --app app create-admin
    """
    import getpass

    email = input("Yonetici e-postasi: ").strip().lower()
    if not email:
        print("E-posta bos olamaz.")
        return

    if User.query.filter_by(email=email).first():
        print(f"'{email}' ile zaten bir hesap var.")
        return

    full_name = input("Ad soyad: ").strip() or "Kampus Koordinatoru"

    password = getpass.getpass("Sifre (en az 6 karakter): ")
    if len(password) < 6:
        print("Sifre en az 6 karakter olmali.")
        return
    if password != getpass.getpass("Sifre (tekrar): "):
        print("Sifreler eslesmiyor.")
        return

    db.session.add(User(
        email=email,
        password_hash=generate_password_hash(password),
        role="admin",
        full_name=full_name,
    ))
    db.session.commit()
    print(f"Yonetici olusturuldu: {email}")
    print("Giris: /admin/giris")


@app.cli.command("seed-demo")
def seed_demo():
    """Tanitim icin UYDURMA ogrenci verisi olusturur.

    Gercek kisisel veri iceren veritabani sunucuya hic gonderilmez
    (.dockerignore); dagitim bos bir veritabaniyla acilir. Bu komut,
    aray�z� dolu gostermek icin tamamen kurgusal kayitlar uretir.

    Kullanim:  flask --app app seed-demo
    """
    import random
    from datetime import timedelta

    if User.query.filter(User.email.like("%@ornek.edu.tr")).first():
        print("Demo verisi zaten var. Once temizlemek icin: flask --app app clear-demo")
        return

    random.seed(42)   # her calistirmada ayni sonuc

    adlar = ["Elif", "Yusuf", "Zeynep", "Mert", "Ayse", "Burak", "Deniz", "Emre",
             "Selin", "Kaan", "Irem", "Ozan", "Ece", "Baris", "Nehir", "Tolga",
             "Melis", "Arda", "Sude", "Efe", "Derya", "Cem", "Buse", "Hakan",
             "Pinar", "Onur", "Gizem", "Serkan"]
    soyadlar = ["Yilmaz", "Demir", "Kaya", "Celik", "Sahin", "Aydin", "Ozturk",
                "Arslan", "Dogan", "Kilic", "Aslan", "Cetin", "Kara", "Koc"]
    okullar = ["Kirikkale Universitesi", "Yalova Universitesi", "Ege Universitesi",
               "Anadolu Universitesi", "Karadeniz Teknik Universitesi"]
    sirketler = ["Teknoloji A.S.", "Veri Sistemleri", "Fiber Net", "Mavi Yazilim",
                 "Kuzey Telekom", "Akilli Sebeke"]
    pozisyonlar = ["Stajyer Yazilim Gelistirici", "Ag Teknisyeni Stajyeri",
                   "Veri Analisti Stajyeri", "Saha Destek Stajyeri"]
    sertifikalar = [("Ag Temelleri", "Cisco"), ("Bulut Temelleri", "AWS"),
                    ("Veri Analizi", "Google"), ("Siber Guvenlik 101", "TUBITAK")]
    projeler = [("Kampus Ag Simulasyonu", "Python, NS-3"),
                ("Fiber Kesinti Haritasi", "Flask, Leaflet"),
                ("Ogrenci Yoklama Sistemi", "Django, SQLite"),
                ("Sensor Veri Panosu", "Python, Grafana")]

    bolumler = [d.name for d in Department.query.all()] or ["Fiber Teknolojisi"]
    sifre = generate_password_hash("demo1234")
    bugun = datetime.now()

    # Paylasilan ornek transkript (gercek bir belge degil)
    os.makedirs(PHOTO_FOLDER, exist_ok=True)
    os.makedirs(TRANSCRIPT_FOLDER, exist_ok=True)
    ornek_transkript = "ornek_transkript.pdf"
    yol = os.path.join(TRANSCRIPT_FOLDER, ornek_transkript)
    if not os.path.exists(yol):
        from reportlab.pdfgen import canvas
        c = canvas.Canvas(yol)
        c.setFont("Helvetica-Bold", 20)
        c.drawString(70, 760, "ORNEK TRANSKRIPT")
        c.setFont("Helvetica", 11)
        c.drawString(70, 730, "Bu belge tanitim amaciyla uretilmistir.")
        c.drawString(70, 712, "Gercek bir ogrenciye ait degildir.")
        c.save()

    olusan = 0
    for i in range(28):
        ad = f"{adlar[i % len(adlar)]} {random.choice(soyadlar)}"
        eposta = f"ogrenci{i + 1:02d}@ornek.edu.tr"

        # Doluluk cesitliligi: bazilari eksik profil, bazilari eksiksiz
        seviye = i % 4          # 0=cok eksik, 3=eksiksiz
        ogr = User(
            email=eposta,
            password_hash=sifre,
            role="student",
            full_name=ad,
            department=random.choice(bolumler),
            phone=f"05{random.randint(10, 59)}{random.randint(1000000, 9999999)}",
            summary=("Kariyerine aglar ve veri alaninda devam etmek isteyen "
                     "son sinif ogrencisi.") if seviye >= 1 else None,
            skills=", ".join(random.sample(
                ["Python", "SQL", "Linux", "Ag Yonetimi", "Excel", "Git",
                 "Fiber Optik", "Ingilizce"], k=random.randint(3, 5))
            ) if seviye >= 1 else None,
            transcript_filename=ornek_transkript if seviye >= 2 else None,
            created_at=bugun - timedelta(days=random.randint(1, 300)),
        )
        db.session.add(ogr)
        db.session.flush()

        bitis = random.randint(2023, 2027)
        db.session.add(Education(
            student_id=ogr.id, degree_type="Lisans",
            school=random.choice(okullar), department=ogr.department,
            gpa=f"{random.uniform(2.1, 3.95):.2f}",
            start_year=str(bitis - 4), end_year=str(bitis),
        ))
        if seviye >= 2:
            sirket = random.choice(sirketler)
            db.session.add(Experience(
                student_id=ogr.id, company=sirket,
                position=random.choice(pozisyonlar),
                start_date="Haz 2025", end_date="Agu 2025",
                description=f"{sirket} bunyesinde yaz stajini tamamladi.",
            ))
        if seviye >= 3:
            sad, kurum = random.choice(sertifikalar)
            db.session.add(Certificate(
                student_id=ogr.id, name=sad, institution=kurum, date="2025"))
            pad, tek = random.choice(projeler)
            db.session.add(Project(
                student_id=ogr.id, title=pad, tech_stack=tek,
                description="Donem projesi kapsaminda gelistirildi."))
        olusan += 1

    # Tanitim icin onayli bir kurum hesabi
    if not User.query.filter_by(email="demo@ornek.com").first():
        db.session.add(User(
            email="demo@ornek.com", password_hash=sifre, role="company",
            company_name="Ornek Kurum A.S.", contact_person="Demo Yetkili",
            is_approved=True, created_at=bugun,
        ))

    # Onay ekraninda gosterilecek, onay BEKLEYEN bir kurum
    if not User.query.filter_by(email="bekleyen@ornek.com").first():
        db.session.add(User(
            email="bekleyen@ornek.com", password_hash=sifre, role="company",
            company_name="Bekleyen Kurum Ltd.", contact_person="Aday Yetkili",
            is_approved=False, created_at=bugun,
        ))

    db.session.commit()
    print(f"{olusan} uydurma ogrenci olusturuldu.")
    print("  Kurum (onayli) : demo@ornek.com / demo1234")
    print("  Kurum (bekleyen): bekleyen@ornek.com")
    print("  Ogrenci         : ogrenci01@ornek.edu.tr / demo1234")
    print("\nYonetici hesabi ayrica olusturulmali: flask --app app create-admin")


@app.cli.command("clear-demo")
def clear_demo():
    """seed-demo ile olusturulan uydurma kayitlari siler."""
    demo = User.query.filter(
        db.or_(User.email.like("%@ornek.edu.tr"), User.email.like("%@ornek.com"))
    ).all()
    for u in demo:
        db.session.delete(u)      # cascade ile CV kayitlari da gider
    db.session.commit()
    print(f"{len(demo)} demo kaydi silindi.")
