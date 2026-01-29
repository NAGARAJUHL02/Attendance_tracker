from flask import Flask, render_template, request, redirect, url_for, send_file
from flask_sqlalchemy import SQLAlchemy
import datetime
import csv
import io
import os

BASE_DIR = os.path.dirname(__file__)
DB_PATH = os.path.join(BASE_DIR, 'attendance.db')

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{DB_PATH}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)


class Class(db.Model):
    __tablename__ = 'classes'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    students = db.relationship('Student', backref='klass', cascade='all, delete-orphan')


class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    klass_id = db.Column(db.Integer, db.ForeignKey('classes.id'), nullable=False)
    attendances = db.relationship('Attendance', backref='student', cascade='all, delete-orphan')


class Attendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(16), nullable=False)  # present / absent / late / excused


with app.app_context():
    db.create_all()


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/classes')
def list_classes():
    classes = Class.query.order_by(Class.name).all()
    return render_template('classes.html', classes=classes)


@app.route('/class/create', methods=['POST'])
def create_class():
    name = request.form.get('name')
    if name:
        klass = Class(name=name.strip())
        db.session.add(klass)
        db.session.commit()
    return redirect(url_for('list_classes'))


@app.route('/class/<int:class_id>')
def view_class(class_id):
    klass = Class.query.get_or_404(class_id)
    today = datetime.date.today()
    # load today's attendance keyed by student id
    attendance = {a.student_id: a for a in Attendance.query.filter_by(date=today).join(Student).filter(Student.klass_id == class_id).all()}
    return render_template('class.html', klass=klass, attendance=attendance, today=today)


@app.route('/class/<int:class_id>/add_student', methods=['POST'])
def add_student(class_id):
    name = request.form.get('student_name')
    if name:
        student = Student(name=name.strip(), klass_id=class_id)
        db.session.add(student)
        db.session.commit()
    return redirect(url_for('view_class', class_id=class_id))


@app.route('/class/<int:class_id>/mark', methods=['POST'])
def mark_attendance(class_id):
    today = datetime.date.today()
    # expected form: present[]=<student_id>
    present_ids = request.form.getlist('present')
    # remove any existing attendance records for today for this class (simple approach)
    students = Student.query.filter_by(klass_id=class_id).all()
    student_ids = [s.id for s in students]
    Attendance.query.filter(Attendance.date == today).filter(Attendance.student_id.in_(student_ids)).delete(synchronize_session=False)
    for sid in student_ids:
        status = 'present' if str(sid) in present_ids else 'absent'
        db.session.add(Attendance(student_id=sid, date=today, status=status))
    db.session.commit()
    return redirect(url_for('view_class', class_id=class_id))


@app.route('/export/class/<int:class_id>/csv')
def export_csv(class_id):
    klass = Class.query.get_or_404(class_id)
    # gather attendances for class
    rows = []
    students = Student.query.filter_by(klass_id=class_id).order_by(Student.name).all()
    dates = sorted({a.date for s in students for a in s.attendances})

    header = ['student'] + [d.isoformat() for d in dates]
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(header)
    for s in students:
        row = [s.name]
        for d in dates:
            att = next((a for a in s.attendances if a.date == d), None)
            row.append(att.status if att else '')
        writer.writerow(row)

    output.seek(0)
    return send_file(io.BytesIO(output.getvalue().encode('utf-8')), mimetype='text/csv', as_attachment=True, download_name=f'{klass.name}-attendance.csv')


if __name__ == '__main__':
    # Read host/port from environment so hosting platforms (Render, Heroku, etc.) can bind correctly
    port = int(os.environ.get('PORT', '5000'))
    host = os.environ.get('HOST', '0.0.0.0')
    debug_env = os.environ.get('FLASK_DEBUG', '')
    debug = debug_env.lower() in ('1', 'true', 'yes')
    print(f"Starting app on {host}:{port} (debug={debug})")
    app.run(host=host, port=port, debug=debug)