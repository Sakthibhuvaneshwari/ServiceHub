from flask_login import login_required 
import os, uuid
from dotenv import load_dotenv
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO, emit, join_room
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

BASE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE, ".env"))
app = Flask(__name__)
app.config["SECRET_KEY"] = "change-this-secret-key"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(BASE, "servicehub.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024
db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet")

UPLOAD_ROOT = os.path.join(BASE, "uploads")
ALLOWED_IMAGES = {"png","jpg","jpeg","webp"}

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    role = db.Column(db.String(20), nullable=False)  # customer/provider
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(160), unique=True, nullable=False)
    phone = db.Column(db.String(30), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    address = db.Column(db.String(300), nullable=False)
    service_type = db.Column(db.String(30))          # provider only
    specific_work = db.Column(db.String(300))
    charge = db.Column(db.Float, default=0)
    profile_photo = db.Column(db.String(300))
    id_type = db.Column(db.String(80), nullable=False)
    id_proof = db.Column(db.String(300), nullable=False)
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    profile_complete = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class WorkImage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    provider_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    before_image = db.Column(db.String(300), nullable=False)
    after_image = db.Column(db.String(300), nullable=False)
    title = db.Column(db.String(200))
    provider = db.relationship("User", backref="work_images")

class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    title = db.Column(db.String(160), nullable=False)
    message = db.Column(db.String(500), nullable=False)
    booking_id = db.Column(db.Integer, db.ForeignKey("booking.id"), nullable=True)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user = db.relationship("User", foreign_keys=[user_id])

class Booking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    provider_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    status = db.Column(db.String(30), default="requested")
    customer_address = db.Column(db.String(300), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    customer_lat = db.Column(db.Float)
    customer_lng = db.Column(db.Float)
    provider_lat = db.Column(db.Float)
    provider_lng = db.Column(db.Float)
    customer = db.relationship("User", foreign_keys=[customer_id])
    provider = db.relationship("User", foreign_keys=[provider_id])

class Review(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(db.Integer, db.ForeignKey("booking.id"), nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    provider_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    rating = db.Column(db.Integer, nullable=False)
    feedback = db.Column(db.Text, nullable=False)
    work_description = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    customer = db.relationship("User", foreign_keys=[customer_id])
    provider = db.relationship("User", foreign_keys=[provider_id])

def save_upload(file, folder):
    if not file or not file.filename:
        return None
    ext = file.filename.rsplit(".",1)[-1].lower()
    if ext not in ALLOWED_IMAGES:
        return None
    filename = secure_filename(str(uuid.uuid4()) + "." + ext)
    path = os.path.join(UPLOAD_ROOT, folder, filename)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    file.save(path)
    return f"uploads/{folder}/{filename}"


def current_user():
    uid = session.get("user_id")
    return db.session.get(User, uid) if uid else None

@app.route("/")
def index():
    return render_template("index.html", user=current_user())

@app.route("/register/<role>", methods=["GET","POST"])
def register(role):
    if role not in ("customer","provider"):
        return redirect(url_for("index"))
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        if User.query.filter_by(email=email).first():
            flash("Email already registered.", "error")
            return redirect(request.url)
        id_proof = save_upload(request.files.get("id_proof"), "id_proof")
        if not id_proof:
            flash("Valid ID proof image is required.", "error")
            return redirect(request.url)
        profile_photo = save_upload(request.files.get("profile_photo"), "profile") if role=="provider" else None
        user = User(
            role=role, name=request.form["name"].strip(), email=email,
            phone=request.form["phone"].strip(),
            password_hash=generate_password_hash(request.form["password"]),
            address=request.form["address"].strip(),
            service_type=request.form.get("service_type") if role=="provider" else request.form.get("work_needed"),
            id_type=request.form["id_type"], id_proof=id_proof,
            profile_photo=profile_photo
        )
        db.session.add(user); db.session.commit()
        session["user_id"] = user.id
        return redirect(url_for("dashboard"))
    return render_template("register.html", role=role)

@app.route("/login/<role>", methods=["GET","POST"])
def login(role):
    if role not in ("customer","provider"):
        return redirect(url_for("index"))
    if request.method == "POST":
        user = User.query.filter_by(email=request.form["email"].strip().lower(), role=role).first()
        if not user or not check_password_hash(user.password_hash, request.form["password"]):
            flash("Invalid email or password.", "error")
            return redirect(request.url)
        session["user_id"] = user.id
        return redirect(url_for("dashboard"))
    return render_template("login.html", role=role)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

@app.route("/dashboard")
def dashboard():
    user = current_user()
    if not user: return redirect(url_for("index"))
    if user.role == "provider":
        reviews = Review.query.filter_by(provider_id=user.id).order_by(Review.created_at.desc()).all()
        bookings = Booking.query.filter_by(provider_id=user.id).order_by(Booking.created_at.desc()).all()
        avg = round(sum(r.rating for r in reviews)/len(reviews),1) if reviews else 0
        return render_template("provider_dashboard.html", user=user, reviews=reviews, bookings=bookings, avg=avg)
    bookings = Booking.query.filter_by(customer_id=user.id).order_by(Booking.created_at.desc()).all()
    return render_template("customer_dashboard.html", user=user, bookings=bookings)

@app.route("/providers")
def providers():
    user=current_user()
    if not user or user.role!="customer": return jsonify({"error":"login required"}),401
    service=request.args.get("service", user.service_type or "")
    rows=User.query.filter_by(role="provider", service_type=service).all()
    customer_lat=request.args.get("lat",type=float); customer_lng=request.args.get("lng",type=float)
    def city(address):
        parts=[x.strip().lower() for x in (address or "").split(",") if x.strip()]
        return parts[-1] if parts else ""
    customer_city=city(user.address)
    def distance(a,b,c,d):
        from math import radians,sin,cos,asin,sqrt
        if None in (a,b,c,d): return None
        R=6371; x=radians(c-a); y=radians(d-b)
        q=sin(x/2)**2+cos(radians(a))*cos(radians(c))*sin(y/2)**2
        return 2*R*asin(sqrt(q))
    data=[]
    for p in rows:
        dist=distance(customer_lat,customer_lng,p.latitude,p.longitude)
        if customer_lat is not None and customer_lng is not None and (dist is None or dist>100): continue
        reviews=Review.query.filter_by(provider_id=p.id).order_by(Review.created_at.desc()).all(); avg=round(sum(r.rating for r in reviews)/len(reviews),1) if reviews else 0
        review_items=[{"customer_name":r.customer.name,"rating":r.rating,"work_description":r.work_description or "Service work","feedback":r.feedback,"created_at":r.created_at.strftime("%d %b %Y")} for r in reviews]
        data.append({"id":p.id,"name":p.name,"phone":p.phone,"service_type":p.service_type,"specific_work":p.specific_work,"charge":p.charge,"address":p.address,"same_city":city(p.address)==customer_city,"distance_km":round(dist,1) if dist is not None else None,"lat":p.latitude,"lng":p.longitude,"profile_photo":"/"+p.profile_photo if p.profile_photo else None,"work_images":[{"before":"/"+w.before_image,"after":"/"+w.after_image,"title":w.title} for w in p.work_images],"rating":avg,"reviews":len(reviews),"review_items":review_items})
    data.sort(key=lambda x:(0 if x["same_city"] else 1,x["distance_km"] if x["distance_km"] is not None else 999999,-x["rating"]))
    return jsonify(data)

@app.route("/api/provider/profile", methods=["POST"])
def provider_profile():
    user=current_user()
    if not user or user.role!="provider": return jsonify({"error":"Unauthorized"}),401
    user.specific_work=request.form.get("specific_work","").strip()
    try: user.charge=float(request.form.get("charge",0))
    except: user.charge=0
    user.profile_photo=save_upload(request.files.get("profile_photo"),"profile") or user.profile_photo
    user.latitude=float(request.form["latitude"]) if request.form.get("latitude") else user.latitude
    user.longitude=float(request.form["longitude"]) if request.form.get("longitude") else user.longitude
    user.profile_complete=bool(user.specific_work and user.charge and user.latitude and user.longitude and user.profile_photo)
    db.session.commit()
    return jsonify({"ok":True,"profile_complete":user.profile_complete})

@app.route("/api/provider/work", methods=["POST"])
def add_work():
    user=current_user()
    if not user or user.role!="provider": return jsonify({"error":"Unauthorized"}),401
    before=save_upload(request.files.get("before"),"work")
    after=save_upload(request.files.get("after"),"work")
    if not before or not after: return jsonify({"error":"Both images are required"}),400
    w=WorkImage(provider_id=user.id,before_image=before,after_image=after,title=request.form.get("title",""))
    db.session.add(w); db.session.commit()
    return jsonify({"ok":True})

def create_notification(user_id, title, message, booking_id=None):
    n = Notification(user_id=user_id, title=title, message=message, booking_id=booking_id)
    db.session.add(n)
    db.session.flush()
    socketio.emit("new_notification", {
        "id": n.id, "title": title, "message": message, "booking_id": booking_id,
        "created_at": n.created_at.strftime("%d %b %I:%M %p")
    }, room=f"user_{user_id}")
    return n

@app.route("/api/notifications")
def notifications():
    user = current_user()
    if not user:
        return jsonify({"error": "Login required"}), 401
    rows = Notification.query.filter_by(user_id=user.id).order_by(Notification.created_at.desc()).limit(30).all()
    unread = Notification.query.filter_by(user_id=user.id, is_read=False).count()
    return jsonify({"unread": unread, "items": [{
        "id": n.id, "title": n.title, "message": n.message, "booking_id": n.booking_id,
        "is_read": n.is_read, "created_at": n.created_at.strftime("%d %b %I:%M %p")
    } for n in rows]})

@app.route("/api/notifications/read", methods=["POST"])
def mark_notifications_read():
    user = current_user()
    if not user:
        return jsonify({"error": "Login required"}), 401
    data = request.get_json(silent=True) or {}
    if data.get("id"):
        n = Notification.query.filter_by(id=int(data["id"]), user_id=user.id).first()
        if n:
            n.is_read = True
    else:
        Notification.query.filter_by(user_id=user.id, is_read=False).update({"is_read": True})
    db.session.commit()
    return jsonify({"ok": True})

@app.route("/api/booking", methods=["POST"])
def create_booking():
    user=current_user()
    if not user or user.role!="customer": return jsonify({"error":"Unauthorized"}),401
    data=request.get_json()
    provider=db.session.get(User,int(data["provider_id"]))
    if not provider: return jsonify({"error":"Provider not found"}),404
    b=Booking(customer_id=user.id,provider_id=provider.id,status="requested",
              customer_address=user.address,customer_lat=data.get("lat"),customer_lng=data.get("lng"),
              provider_lat=provider.latitude,provider_lng=provider.longitude)
    db.session.add(b); db.session.commit()
    create_notification(provider.id, "New booking request", f"{user.name} booked your {provider.service_type} service.", b.id)
    create_notification(user.id, "Booking sent", f"Your booking request was sent to {provider.name}.", b.id)
    socketio.emit("booking_notification",{"message":f"New booking from {user.name}","booking_id":b.id},room=f"user_{provider.id}")
    return jsonify({"ok":True,"booking_id":b.id,"provider_phone":provider.phone,"whatsapp_url":"https://wa.me/{normalize_phone(provider.phone).replace('+','')}?text=Hi%20{provider.name.replace(' ','%20')}%2C%20I%20booked%20your%20service%20on%20ServiceHub.%20Booking%20%23{b.id}."})

@app.route("/api/booking/<int:bid>/status", methods=["POST"])
def booking_status(bid):
    user=current_user(); b=db.session.get(Booking,bid)
    if not user or not b: return jsonify({"error":"Not found"}),404
    if user.id not in (b.customer_id,b.provider_id): return jsonify({"error":"Forbidden"}),403
    status=(request.get_json(silent=True) or {}).get("status")
    allowed={"accepted","rejected","on_the_way","started","completed","cancelled"}
    if status not in allowed: return jsonify({"error":"Invalid status"}),400
    b.status=status
    db.session.commit()
    other=b.customer_id if user.id==b.provider_id else b.provider_id
    provider_message = {
        "accepted": "I am accepting your booking request. See you soon!",
        "rejected": "Sorry, I am unable to accept this booking request.",
        "on_the_way": "I am on the way to your location.",
        "started": "I have started the work.",
        "completed": "Your service has been completed. Thank you!",
        "cancelled": "This booking has been cancelled."
    }.get(status, f"Booking #{b.id} is now {status.replace('_',' ')}.")
    message = provider_message if user.id == b.provider_id else f"Professional update: {provider_message}"
    create_notification(other, "Booking update", message, b.id)
    socketio.emit("status_update", {"booking_id":b.id,"status":status,"message":message}, room=f"user_{other}")
    whatsapp_url=None
    if user.id==b.provider_id and status in {"accepted","rejected","on_the_way","started","completed"}:
        import urllib.parse
        wa_text=f"Hi {b.customer.name}, {message} Booking #{b.id} - ServiceHub."
        number="".join(ch for ch in (b.customer.phone or "") if ch.isdigit())
        whatsapp_url=f"https://wa.me/{number}?text={urllib.parse.quote(wa_text)}" if number else None
    return jsonify({"ok":True,"status":status,"message":message,"whatsapp_url":whatsapp_url})

@app.route("/api/booking/<int:bid>/location", methods=["POST"])
@login_required
def update_booking_location(bid):
    b = Booking.query.get_or_404(bid)
    if current_user.id not in (b.customer_id, b.provider_id):
        return jsonify({"error":"Unauthorized"}), 403
    data = request.get_json(silent=True) or {}
    try:
        lat, lng = float(data.get("lat")), float(data.get("lng"))
    except (TypeError, ValueError):
        return jsonify({"error":"Valid coordinates are required"}), 400
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        return jsonify({"error":"Invalid coordinates"}), 400
    if current_user.id == b.provider_id:
        b.provider_lat, b.provider_lng = lat, lng
        target, role = b.customer_id, "provider"
    else:
        b.customer_lat, b.customer_lng = lat, lng
        target, role = b.provider_id, "customer"
    db.session.commit()
    socketio.emit("location_update", {
        "booking_id": b.id, "role": role, "lat": lat, "lng": lng,
        "updated_at": datetime.utcnow().strftime("%d %b %Y %I:%M:%S %p")
    }, room=f"user_{target}")
    return jsonify({"success":True,"lat":lat,"lng":lng,"role":role})

@app.route("/api/review", methods=["POST"])
def add_review():
    user=current_user()
    if not user or user.role!="customer": return jsonify({"error":"Unauthorized"}),401
    data=request.get_json(); b=db.session.get(Booking,int(data["booking_id"]))
    if not b or b.customer_id!=user.id or b.status!="completed": return jsonify({"error":"Review allowed after completion"}),400
    if Review.query.filter_by(booking_id=b.id).first(): return jsonify({"error":"Already reviewed"}),400
    rating=int(data.get("rating",0)); feedback=str(data.get("feedback","")).strip(); work_description=str(data.get("work_description","")).strip()
    if rating < 1 or rating > 5 or not feedback or not work_description: return jsonify({"error":"Rating, work details and feedback are required"}),400
    r=Review(booking_id=b.id,customer_id=user.id,provider_id=b.provider_id,
             rating=rating,feedback=feedback,work_description=work_description)
    db.session.add(r); db.session.commit()
    create_notification(b.provider_id, "New customer review", f"You received a {r.rating}/5 review from {user.name}.", b.id)
    socketio.emit("review_notification",{"booking_id":b.id,"rating":r.rating,"feedback":r.feedback},room=f"user_{b.provider_id}")
    return jsonify({"ok":True})

@app.route("/api/chatbot", methods=["POST"])
def chatbot():
    user=current_user()
    if not user:
        return jsonify({"error":"Login required"}),401
    data=request.get_json(silent=True) or {}
    message=str(data.get("message","")).strip().lower()
    if not message:
        return jsonify({"reply":"Hi! How can I help you with ServiceHub?"})
    if any(x in message for x in ["hello","hi","hey"]):
        reply="Hi! 👋 I can help with booking, provider status, tracking and reviews."
    elif "book" in message:
        reply="Choose Plumber, Electrician or Carpenter, select a nearby professional and click Book now."
    elif "accept" in message or "accepted" in message:
        reply="When the professional accepts your request, the booking status will change to Accepted immediately."
    elif "reject" in message or "rejected" in message:
        reply="If a professional rejects your request, you can choose another nearby professional."
    elif "track" in message or "location" in message:
        reply="After the professional starts travelling, use the Track button in My bookings to view their shared location."
    elif "review" in message or "rating" in message or "feedback" in message:
        reply="After the booking is completed, use Rate service to give a 1–5 star rating and feedback."
    elif "status" in message:
        reply="Booking statuses are Requested → Accepted → On the way → Started → Completed."
    else:
        reply="I can help with booking, acceptance/rejection, provider status, tracking and reviews. Try asking one of these."
    return jsonify({"reply":reply})

@socketio.on("connect")
def connected(auth=None):
    user=current_user()
    if user: join_room(f"user_{user.id}")

@app.route("/uploads/<path:path>")
def uploaded(path):
    from flask import send_from_directory
    return send_from_directory(UPLOAD_ROOT, path)

with app.app_context():
    db.create_all()
    # Lightweight migration for existing installations.
    from sqlalchemy import inspect, text
    review_cols = {c["name"] for c in inspect(db.engine).get_columns("review")}
    if "work_description" not in review_cols:
        with db.engine.begin() as conn:
            conn.execute(text("ALTER TABLE review ADD COLUMN work_description TEXT"))
    cols = {c["name"] for c in inspect(db.engine).get_columns("user")}
    if "phone" not in cols:
        with db.engine.begin() as conn:
            conn.execute(text("ALTER TABLE user ADD COLUMN phone VARCHAR(30) DEFAULT ''"))


if __name__=="__main__":
    socketio.run(app, host="0.0.0.0", port=5001, debug=True)
