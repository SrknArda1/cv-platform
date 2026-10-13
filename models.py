from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin

db = SQLAlchemy()

class Department(db.Model):
    __tablename__ = "departments"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)

    def __repr__(self):
        return f"<{self.name}>"


class User(UserMixin, db.Model):
    """Hem öğrenci hem kurum hesapları burada tutulur, 'role' alanı ile ayrılır."""
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # 'student' veya 'company'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Öğrenciye özel alanlar
    full_name = db.Column(db.String(255))
    department = db.Column(db.String(120))
    phone = db.Column(db.String(50))
    summary = db.Column(db.Text)  # Kısa profesyonel özet
    transcript_filename = db.Column(db.String(255))
    photo_filename = db.Column(db.String(255))
    skills = db.Column(db.Text)

    # Kuruma özel alanlar
    company_name = db.Column(db.String(255))
    contact_person = db.Column(db.String(255))
    is_approved = db.Column(db.Boolean, default=False)

    # Onay kaydı: kurum hesabı öğrencilerin kişisel verisine erişim kazandığı
    # için bu kararın kim tarafından, ne zaman verildiği kayda geçer.
    approved_at = db.Column(db.DateTime)
    approved_by_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    approved_by = db.relationship(
        "User", remote_side=[id], foreign_keys=[approved_by_id], uselist=False
    )

    # Başvuru reddi (kuruma ait)
    #
    # Kurum hesabının üç durumu var ve ikisi `is_approved` ile anlatılamaz:
    #   bekliyor   -> is_approved=False, rejected_at=None
    #   onaylı     -> is_approved=True
    #   reddedildi -> is_approved=False, rejected_at dolu
    #
    # Reddi ayrı tutmanın sebebi: hesabı silmek yerine işaretlemek, kuruma
    # net bir cevap verir (sonsuza kadar "bekleniyor" görmez) ve kararın
    # kaydı kalır. Yeniden değerlendirilebilir.
    rejected_at = db.Column(db.DateTime)
    rejected_by_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    rejected_by = db.relationship(
        "User", remote_side=[id], foreign_keys=[rejected_by_id], uselist=False
    )
    rejection_reason = db.Column(db.String(500))

    @property
    def basvuru_durumu(self):
        """'onayli' | 'reddedildi' | 'bekliyor' — şablonlarda kullanılır."""
        if self.is_approved:
            return "onayli"
        if self.rejected_at:
            return "reddedildi"
        return "bekliyor"

    # Transkript doğrulama (öğrenciye ait)
    #
    # Herkes herhangi bir PDF yükleyip "transkriptim" diyebilir. Koordinatör
    # belgeyi açıp doğruladığında kurum tarafında "VAR" yerine "DOĞRULANDI"
    # görünür — platformun kuruma sunduğu güven buna dayanır.
    #
    # ÖNEMLİ: Öğrenci yeni bir transkript yüklediğinde bu alan sıfırlanır
    # (bkz. student_cv_form). Aksi halde doğrulanmış belgeyi değiştirip
    # doğrulanmış görünmeye devam edebilirdi.
    transcript_verified = db.Column(db.Boolean, default=False, nullable=False)
    transcript_verified_at = db.Column(db.DateTime)
    transcript_verified_by_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    transcript_verified_by = db.relationship(
        "User", remote_side=[id], foreign_keys=[transcript_verified_by_id], uselist=False
    )

    # İlişkili kayıtlar (öğrenci CV blokları)
    educations = db.relationship(
        "Education", backref="student", cascade="all, delete-orphan",
        order_by="Education.id"
    )
    experiences = db.relationship(
        "Experience", backref="student", cascade="all, delete-orphan",
        order_by="Experience.id"
    )
    certificates = db.relationship(
        "Certificate", backref="student", cascade="all, delete-orphan",
        order_by="Certificate.id"
    )
    projects = db.relationship(
        "Project", backref="student", cascade="all, delete-orphan",
        order_by="Project.id"
    )

    @property
    def initials(self):
        name = (self.full_name or self.company_name or self.email or "?").strip()
        parts = [p for p in name.split() if p]
        if not parts:
            return "?"
        if len(parts) == 1:
            return parts[0][0].upper()
        return (parts[0][0] + parts[-1][0]).upper()

    @property
    def latest_education(self):
        """En güncel eğitim kaydı — bitiş yılı en büyük olan, yoksa son eklenen."""
        if not self.educations:
            return None

        def year_key(edu):
            try:
                return int(str(edu.end_year or "").strip()[:4])
            except (ValueError, TypeError):
                return -1

        return max(self.educations, key=year_key)

    @property
    def gpa_display(self):
        """Aday havuzunda gösterilecek ortalama (ham metin, girildiği gibi)."""
        edu = self.latest_education
        gpa = (edu.gpa or "").strip() if edu else ""
        return gpa or None

    @property
    def gpa_value(self):
        """Sıralama için sayısal ortalama. gpa metin alanı olduğu için
        '3,42' gibi virgüllü girişleri de tolere eder; çözülemezse None."""
        gpa = self.gpa_display
        if not gpa:
            return None
        try:
            return float(gpa.replace(",", "."))
        except ValueError:
            return None

    def profile_completion(self):
        """Öğrenci profilinin doluluk yüzdesini hesaplar (0-100)."""
        if self.role != "student":
            return 100
        score = 0
        if self.full_name and self.department and self.phone and self.summary:
            score += 25
        if self.educations:
            score += 25
        if self.transcript_filename:
            score += 20
        if self.experiences or self.projects:
            score += 15
        if self.certificates:
            score += 15
        return min(score, 100)

    def missing_sections(self):
        """Tamamlanması gereken bölümlerin okunabilir listesi."""
        missing = []
        if not (self.full_name and self.department and self.phone and self.summary):
            missing.append("Genel bilgiler ve özet")
        if not self.educations:
            missing.append("Eğitim geçmişi")
        if not self.transcript_filename:
            missing.append("Transkript")
        if not (self.experiences or self.projects):
            missing.append("Deneyim veya proje")
        if not self.certificates:
            missing.append("Sertifikalar")
        return missing

    def is_profile_complete(self):
        return self.profile_completion() >= 85


class Education(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    degree_type = db.Column(db.String(50))
    school = db.Column(db.String(255), nullable=False)
    department = db.Column(db.String(255))
    gpa = db.Column(db.String(10))
    start_year = db.Column(db.String(10))
    end_year = db.Column(db.String(10))


class Experience(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    company = db.Column(db.String(255), nullable=False)
    position = db.Column(db.String(255))
    start_date = db.Column(db.String(30))
    end_date = db.Column(db.String(30))
    description = db.Column(db.Text)


class Certificate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    name = db.Column(db.String(255), nullable=False)
    institution = db.Column(db.String(255))
    date = db.Column(db.String(30))


class Project(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text)
    tech_stack = db.Column(db.String(255))
    link = db.Column(db.String(255))
