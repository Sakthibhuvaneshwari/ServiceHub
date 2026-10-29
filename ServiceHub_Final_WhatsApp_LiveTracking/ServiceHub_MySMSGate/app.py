
import os
import uuid
from datetime import datetime
from urllib.parse import quote

from dotenv import load_dotenv
from flask import (
    Flask, render_template, request, redirect,
    url_for, session, jsonify, flash, send_from_directory
)
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO, join_room
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from supabase import create_client
from sqlalchemy import inspect, text


# --------------------------------------------------
# APPLICATION CONFIGURATION
# --------------------------------------------------

BASE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE, ".env"))

app = Flask(__name__)

app.config["SECRET_KEY"] = os.environ.get(
    "SECRET_KEY", "change-this-secret-key"
)
app.config["SQLALCHEMY_DATABASE_URI"] = (
    "sqlite:///" + os.path.join(BASE, "servicehub.db")
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024

db = SQLAlchemy(app)

socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode="eventlet"
)

UPLOAD_ROOT = os.path.join(BASE, "uploads")
ALLOWED_IMAGES = {"png", "jpg", "jpeg", "webp"}


# --------------------------------------------------
# DATABASE MODELS
# --------------------------------------------------

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    role = db.Column(db.String(20), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(160), unique=True, nullable=False)
    phone = db.Column(db.String(30), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    address = db.Column(db.String(300), nullable=False)
    service_type = db.Column(db.String(30))
    specific_work = db.Column(db.String(300))
    charge = db.Column(db.Float, default=0)

    profile_photo = db.Column(db.String(1000))
    id_type = db.Column(db.String(80), nullable=False)
    id_proof = db.Column(db.String(1000))

    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    profile_complete = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class WorkImage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    provider_id = db.Column(
        db.Integer, db.ForeignKey("user.id"), nullable=False
    )
    before_image = db.Column(db.String(1000), nullable=False)
    after_image = db.Column(db.String(1000), nullable=False)
    title = db.Column(db.String(200))

    provider = db.relationship("User", backref="work_images")


class Booking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(
        db.Integer, db.ForeignKey("user.id"), nullable=False
    )
    provider_id = db.Column(
        db.Integer, db.ForeignKey("user.id"), nullable=False
    )

    status = db.Column(db.String(30), default="requested")
    customer_address = db.Column(db.String(300), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    customer_lat = db.Column(db.Float)
    customer_lng = db.Column(db.Float)
    provider_lat = db.Column(db.Float)
    provider_lng = db.Column(db.Float)

    customer = db.relationship("User", foreign_keys=[customer_id])
    provider = db.relationship("User", foreign_keys=[provider_id])


class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("user.id"), nullable=False
    )
    title = db.Column(db.String(160), nullable=False)
    message = db.Column(db.String(500), nullable=False)

    booking_id = db.Column(
        db.Integer, db.ForeignKey("booking.id"), nullable=True
    )

    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship("User", foreign_keys=[user_id])


class Review(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(
        db.Integer, db.ForeignKey("booking.id"), nullable=False
    )
    customer_id = db.Column(
        db.Integer, db.ForeignKey("user.id"), nullable=False
    )
    provider_id = db.Column(
        db.Integer, db.ForeignKey("user.id"), nullable=False
    )

    rating = db.Column(db.Integer, nullable=False)
    feedback = db.Column(db.Text, nullable=False)
    work_description = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    customer = db.relationship("User", foreign_keys=[customer_id])
    provider = db.relationship("User", foreign_keys=[provider_id])


# --------------------------------------------------
# SESSION AUTHENTICATION
# --------------------------------------------------

def current_user():
    uid = session.get("user_id")
    return db.session.get(User, uid) if uid else None


# --------------------------------------------------
# IMAGE URL HELPER
# --------------------------------------------------

def image_url(path):
    if not path:
        return None

    # Supabase public URLs must not receive another slash.
    if path.startswith(("http://", "https://")):
        return path

    # Support old local upload paths.
    return "/" + path.lstrip("/")


# --------------------------------------------------
# SUPABASE IMAGE UPLOAD
# --------------------------------------------------

def save_upload(file, folder):
    if not file or not file.filename:
        return None

    safe_name = secure_filename(file.filename)

    if "." not in safe_name:
        return None

    ext = safe_name.rsplit(".", 1)[-1].lower()

    if ext not in ALLOWED_IMAGES:
        return None

    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_KEY")

    if not supabase_url or not supabase_key:
        app.logger.error(
            "SUPABASE_URL or SUPABASE_KEY is missing."
        )
        return None

    try:
        client = create_client(supabase_url, supabase_key)

        filename = f"{folder}/{uuid.uuid4()}.{ext}"
        content_type = file.mimetype or "application/octet-stream"

        client.storage.from_("servicehub-images").upload(
            filename,
            file.read(),
            file_options={
                "content-type": content_type,
                "upsert": "false"
            }
        )

        public_url = client.storage.from_(
            "servicehub-images"
        ).get_public_url(filename)

        # Support common Supabase SDK return formats.
        if isinstance(public_url, str):
            return public_url

        if isinstance(public_url, dict):
            return (
                public_url.get("publicUrl")
                or public_url.get("publicURL")
            )

        return str(public_url)

    except Exception:
        app.logger.exception("Supabase image upload failed.")
        return None


# --------------------------------------------------
# HOME
# --------------------------------------------------

@app.route("/")
def index():
    return render_template(
        "index.html",
        user=current_user()
    )


# --------------------------------------------------
# REGISTER
# --------------------------------------------------

@app.route("/register/<role>", methods=["GET", "POST"])
def register(role):
    if role not in ("customer", "provider"):
        return redirect(url_for("index"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()

        if not email:
            flash("Email is required.", "error")
            return redirect(request.url)

        if User.query.filter_by(email=email).first():
            flash("Email already registered.", "error")
            return redirect(request.url)

        id_proof = save_upload(
            request.files.get("id_proof"),
            "id_proof"
        )

        if not id_proof:
            flash(
                "Valid ID proof image is required. "
                "Please check the image and Supabase settings.",
                "error"
            )
            return redirect(request.url)

        profile_photo = None

        if role == "provider":
            profile_photo = save_upload(
                request.files.get("profile_photo"),
                "profile"
            )

        user = User(
            role=role,
            name=request.form.get("name", "").strip(),
            email=email,
            phone=request.form.get("phone", "").strip(),
            password_hash=generate_password_hash(
                request.form.get("password", "")
            ),
            address=request.form.get("address", "").strip(),
            service_type=(
                request.form.get("service_type")
                if role == "provider"
                else request.form.get("work_needed")
            ),
            id_type=request.form.get("id_type", "").strip(),
            id_proof=id_proof,
            profile_photo=profile_photo
        )

        db.session.add(user)
        db.session.commit()

        session["user_id"] = user.id

        return redirect(url_for("dashboard"))

    return render_template("register.html", role=role)


# --------------------------------------------------
# LOGIN
# --------------------------------------------------

@app.route("/login/<role>", methods=["GET", "POST"])
def login(role):
    if role not in ("customer", "provider"):
        return redirect(url_for("index"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user = User.query.filter_by(
            email=email,
            role=role
        ).first()

        if not user or not check_password_hash(
            user.password_hash, password
        ):
            flash("Invalid email or password.", "error")
            return redirect(request.url)

        session["user_id"] = user.id

        return redirect(url_for("dashboard"))

    return render_template("login.html", role=role)


# --------------------------------------------------
# LOGOUT
# --------------------------------------------------

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


# --------------------------------------------------
# DASHBOARD
# --------------------------------------------------

@app.route("/dashboard")
def dashboard():
    user = current_user()

    if not user:
        return redirect(url_for("index"))

    if user.role == "provider":
        reviews = Review.query.filter_by(
            provider_id=user.id
        ).order_by(Review.created_at.desc()).all()

        bookings = Booking.query.filter_by(
            provider_id=user.id
        ).order_by(Booking.created_at.desc()).all()

        avg = (
            round(sum(r.rating for r in reviews) / len(reviews), 1)
            if reviews else 0
        )

        return render_template(
            "provider_dashboard.html",
            user=user,
            reviews=reviews,
            bookings=bookings,
            avg=avg
        )

    bookings = Booking.query.filter_by(
        customer_id=user.id
    ).order_by(Booking.created_at.desc()).all()

    return render_template(
        "customer_dashboard.html",
        user=user,
        bookings=bookings
    )


# --------------------------------------------------
# PROVIDER LIST
# --------------------------------------------------

@app.route("/providers")
def providers():
    user = current_user()

    if not user or user.role != "customer":
        return jsonify({"error": "login required"}), 401

    service = request.args.get(
        "service", user.service_type or ""
    )

    rows = User.query.filter_by(
        role="provider",
        service_type=service
    ).all()

    customer_lat = request.args.get("lat", type=float)
    customer_lng = request.args.get("lng", type=float)

    def city(address):
        parts = [
            part.strip().lower()
            for part in (address or "").split(",")
            if part.strip()
        ]
        return parts[-1] if parts else ""

    customer_city = city(user.address)

    def distance(a, b, c, d):
        from math import radians, sin, cos, asin, sqrt

        if None in (a, b, c, d):
            return None

        radius = 6371
        x = radians(c - a)
        y = radians(d - b)

        q = (
            sin(x / 2) ** 2
            + cos(radians(a))
            * cos(radians(c))
            * sin(y / 2) ** 2
        )

        return 2 * radius * asin(sqrt(q))

    data = []

    for provider in rows:
        dist = distance(
            customer_lat,
            customer_lng,
            provider.latitude,
            provider.longitude
        )

        if customer_lat is not None and customer_lng is not None:
            if dist is None or dist > 100:
                continue

        reviews = Review.query.filter_by(
            provider_id=provider.id
        ).order_by(Review.created_at.desc()).all()

        avg = (
            round(sum(r.rating for r in reviews) / len(reviews), 1)
            if reviews else 0
        )

        review_items = [
            {
                "customer_name": review.customer.name,
                "rating": review.rating,
                "work_description": (
                    review.work_description or "Service work"
                ),
                "feedback": review.feedback,
                "created_at": review.created_at.strftime("%d %b %Y")
            }
            for review in reviews
        ]

        data.append({
            "id": provider.id,
            "name": provider.name,
            "phone": provider.phone,
            "service_type": provider.service_type,
            "specific_work": provider.specific_work,
            "charge": provider.charge,
            "address": provider.address,
            "same_city": city(provider.address) == customer_city,
            "distance_km": round(dist, 1) if dist is not None else None,
            "lat": provider.latitude,
            "lng": provider.longitude,

            # Correctly preserve Supabase HTTPS URLs.
            "profile_photo": image_url(provider.profile_photo),

            "work_images": [
                {
                    "before": image_url(work.before_image),
                    "after": image_url(work.after_image),
                    "title": work.title
                }
                for work in provider.work_images
            ],

            "rating": avg,
            "reviews": len(reviews),
            "review_items": review_items
        })

    data.sort(
        key=lambda item: (
            0 if item["same_city"] else 1,
            (
                item["distance_km"]
                if item["distance_km"] is not None
                else 999999
            ),
            -item["rating"]
        )
    )

    return jsonify(data)


# --------------------------------------------------
# PROVIDER PROFILE UPDATE
# --------------------------------------------------

@app.route("/api/provider/profile", methods=["POST"])
def provider_profile():
    user = current_user()

    if not user or user.role != "provider":
        return jsonify({"error": "Unauthorized"}), 401

    user.specific_work = request.form.get(
        "specific_work", ""
    ).strip()

    try:
        user.charge = float(request.form.get("charge", 0))
    except (TypeError, ValueError):
        user.charge = 0

    uploaded_photo = save_upload(
        request.files.get("profile_photo"),
        "profile"
    )

    if uploaded_photo:
        user.profile_photo = uploaded_photo

    try:
        if request.form.get("latitude"):
            user.latitude = float(request.form["latitude"])

        if request.form.get("longitude"):
            user.longitude = float(request.form["longitude"])

    except (TypeError, ValueError):
        return jsonify({"error": "Invalid coordinates"}), 400

    user.profile_complete = bool(
        user.specific_work
        and user.charge > 0
        and user.latitude is not None
        and user.longitude is not None
        and user.profile_photo
    )

    db.session.commit()

    return jsonify({
        "ok": True,
        "profile_complete": user.profile_complete
    })


# --------------------------------------------------
# ADD BEFORE/AFTER WORK IMAGES
# --------------------------------------------------

@app.route("/api/provider/work", methods=["POST"])
def add_work():
    user = current_user()

    if not user or user.role != "provider":
        return jsonify({"error": "Unauthorized"}), 401

    before = save_upload(
        request.files.get("before"),
        "work"
    )

    after = save_upload(
        request.files.get("after"),
        "work"
    )

    if not before or not after:
        return jsonify({
            "error": (
                "Both images are required. "
                "Check Supabase configuration."
            )
        }), 400

    work = WorkImage(
        provider_id=user.id,
        before_image=before,
        after_image=after,
        title=request.form.get("title", "").strip()
    )

    db.session.add(work)
    db.session.commit()

    return jsonify({"ok": True})


# --------------------------------------------------
# NOTIFICATIONS
# --------------------------------------------------

def create_notification(user_id, title, message, booking_id=None):
    notification = Notification(
        user_id=user_id,
        title=title,
        message=message,
        booking_id=booking_id
    )

    db.session.add(notification)
    db.session.flush()

    socketio.emit(
        "new_notification",
        {
            "id": notification.id,
            "title": title,
            "message": message,
            "booking_id": booking_id,
            "created_at": notification.created_at.strftime(
                "%d %b %I:%M %p"
            )
        },
        room=f"user_{user_id}"
    )

    return notification


@app.route("/api/notifications")
def notifications():
    user = current_user()

    if not user:
        return jsonify({"error": "Login required"}), 401

    rows = Notification.query.filter_by(
        user_id=user.id
    ).order_by(Notification.created_at.desc()).limit(30).all()

    unread = Notification.query.filter_by(
        user_id=user.id,
        is_read=False
    ).count()

    return jsonify({
        "unread": unread,
        "items": [
            {
                "id": item.id,
                "title": item.title,
                "message": item.message,
                "booking_id": item.booking_id,
                "is_read": item.is_read,
                "created_at": item.created_at.strftime(
                    "%d %b %I:%M %p"
                )
            }
            for item in rows
        ]
    })


@app.route("/api/notifications/read", methods=["POST"])
def mark_notifications_read():
    user = current_user()

    if not user:
        return jsonify({"error": "Login required"}), 401

    data = request.get_json(silent=True) or {}

    if data.get("id"):
        try:
            notification_id = int(data["id"])
        except (TypeError, ValueError):
            return jsonify({"error": "Invalid notification id"}), 400

        item = Notification.query.filter_by(
            id=notification_id,
            user_id=user.id
        ).first()

        if item:
            item.is_read = True

    else:
        Notification.query.filter_by(
            user_id=user.id,
            is_read=False
        ).update({"is_read": True})

    db.session.commit()

    return jsonify({"ok": True})


# --------------------------------------------------
# CREATE BOOKING
# --------------------------------------------------

@app.route("/api/booking", methods=["POST"])
def create_booking():
    user = current_user()

    if not user or user.role != "customer":
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json(silent=True) or {}

    try:
        provider_id = int(data.get("provider_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "Valid provider_id is required"}), 400

    provider = db.session.get(User, provider_id)

    if not provider or provider.role != "provider":
        return jsonify({"error": "Provider not found"}), 404

    booking = Booking(
        customer_id=user.id,
        provider_id=provider.id,
        status="requested",
        customer_address=user.address,
        customer_lat=data.get("lat"),
        customer_lng=data.get("lng"),
        provider_lat=provider.latitude,
        provider_lng=provider.longitude
    )

    db.session.add(booking)
    db.session.commit()

    create_notification(
        provider.id,
        "New booking request",
        f"{user.name} booked your {provider.service_type} service.",
        booking.id
    )

    create_notification(
        user.id,
        "Booking sent",
        f"Your booking request was sent to {provider.name}.",
        booking.id
    )

    socketio.emit(
        "booking_notification",
        {
            "message": f"New booking from {user.name}",
            "booking_id": booking.id
        },
        room=f"user_{provider.id}"
    )

    number = "".join(
        char for char in (provider.phone or "")
        if char.isdigit()
    )

    wa_text = (
        f"Hi {provider.name}, I booked your service on "
        f"ServiceHub. Booking #{booking.id}."
    )

    whatsapp_url = (
        f"https://wa.me/{number}?text={quote(wa_text)}"
        if number else None
    )

    return jsonify({
        "ok": True,
        "booking_id": booking.id,
        "provider_phone": provider.phone,
        "whatsapp_url": whatsapp_url
    })


# --------------------------------------------------
# UPDATE BOOKING STATUS
# --------------------------------------------------

@app.route("/api/booking/<int:bid>/status", methods=["POST"])
def booking_status(bid):
    user = current_user()
    booking = db.session.get(Booking, bid)

    if not user or not booking:
        return jsonify({"error": "Not found"}), 404

    if user.id not in (booking.customer_id, booking.provider_id):
        return jsonify({"error": "Forbidden"}), 403

    data = request.get_json(silent=True) or {}
    status = data.get("status")

    allowed = {
        "accepted",
        "rejected",
        "on_the_way",
        "started",
        "completed",
        "cancelled"
    }

    if status not in allowed:
        return jsonify({"error": "Invalid status"}), 400

    booking.status = status
    db.session.commit()

    other_user_id = (
        booking.customer_id
        if user.id == booking.provider_id
        else booking.provider_id
    )

    status_messages = {
        "accepted": "I am accepting your booking request. See you soon!",
        "rejected": "Sorry, I am unable to accept this booking request.",
        "on_the_way": "I am on the way to your location.",
        "started": "I have started the work.",
        "completed": "Your service has been completed. Thank you!",
        "cancelled": "This booking has been cancelled."
    }

    provider_message = status_messages[status]

    message = (
        provider_message
        if user.id == booking.provider_id
        else f"Professional update: {provider_message}"
    )

    create_notification(
        other_user_id,
        "Booking update",
        message,
        booking.id
    )

    socketio.emit(
        "status_update",
        {
            "booking_id": booking.id,
            "status": status,
            "message": message
        },
        room=f"user_{other_user_id}"
    )

    whatsapp_url = None

    if (
        user.id == booking.provider_id
        and status in {
            "accepted", "rejected", "on_the_way",
            "started", "completed"
        }
    ):
        number = "".join(
            char for char in (booking.customer.phone or "")
            if char.isdigit()
        )

        wa_text = (
            f"Hi {booking.customer.name}, {message} "
            f"Booking #{booking.id} - ServiceHub."
        )

        if number:
            whatsapp_url = (
                f"https://wa.me/{number}?text={quote(wa_text)}"
            )

    return jsonify({
        "ok": True,
        "status": status,
        "message": message,
        "whatsapp_url": whatsapp_url
    })


# --------------------------------------------------
# LIVE LOCATION
# --------------------------------------------------

@app.route("/api/booking/<int:bid>/location", methods=["POST"])
def update_booking_location(bid):
    # This app uses session-based authentication.
    # Do not use Flask-Login's @login_required here.
    user = current_user()
    booking = db.session.get(Booking, bid)

    if not user or not booking:
        return jsonify({"error": "Not found"}), 404

    if user.id not in (booking.customer_id, booking.provider_id):
        return jsonify({"error": "Unauthorized"}), 403

    data = request.get_json(silent=True) or {}

    try:
        lat = float(data.get("lat"))
        lng = float(data.get("lng"))
    except (TypeError, ValueError):
        return jsonify({
            "error": "Valid coordinates are required"
        }), 400

    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        return jsonify({"error": "Invalid coordinates"}), 400

    if user.id == booking.provider_id:
        booking.provider_lat = lat
        booking.provider_lng = lng
        target_user_id = booking.customer_id
        role = "provider"
    else:
        booking.customer_lat = lat
        booking.customer_lng = lng
        target_user_id = booking.provider_id
        role = "customer"

    db.session.commit()

    socketio.emit(
        "location_update",
        {
            "booking_id": booking.id,
            "role": role,
            "lat": lat,
            "lng": lng,
            "updated_at": datetime.utcnow().strftime(
                "%d %b %Y %I:%M:%S %p"
            )
        },
        room=f"user_{target_user_id}"
    )

    return jsonify({
        "success": True,
        "lat": lat,
        "lng": lng,
        "role": role
    })


# --------------------------------------------------
# ADD REVIEW
# --------------------------------------------------

@app.route("/api/review", methods=["POST"])
def add_review():
    user = current_user()

    if not user or user.role != "customer":
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json(silent=True) or {}

    try:
        booking_id = int(data.get("booking_id"))
        rating = int(data.get("rating", 0))
    except (TypeError, ValueError):
        return jsonify({
            "error": "Valid booking_id and rating are required"
        }), 400

    booking = db.session.get(Booking, booking_id)

    if (
        not booking
        or booking.customer_id != user.id
        or booking.status != "completed"
    ):
        return jsonify({
            "error": "Review allowed after completion"
        }), 400

    if Review.query.filter_by(booking_id=booking.id).first():
        return jsonify({"error": "Already reviewed"}), 400

    feedback = str(data.get("feedback", "")).strip()
    work_description = str(
        data.get("work_description", "")
    ).strip()

    if rating < 1 or rating > 5 or not feedback or not work_description:
        return jsonify({
            "error": "Rating, work details and feedback are required"
        }), 400

    review = Review(
        booking_id=booking.id,
        customer_id=user.id,
        provider_id=booking.provider_id,
        rating=rating,
        feedback=feedback,
        work_description=work_description
    )

    db.session.add(review)
    db.session.commit()

    create_notification(
        booking.provider_id,
        "New customer review",
        f"You received a {review.rating}/5 review from {user.name}.",
        booking.id
    )

    socketio.emit(
        "review_notification",
        {
            "booking_id": booking.id,
            "rating": review.rating,
            "feedback": review.feedback
        },
        room=f"user_{booking.provider_id}"
    )

    return jsonify({"ok": True})


# --------------------------------------------------
# CHATBOT
# --------------------------------------------------

@app.route("/api/chatbot", methods=["POST"])
def chatbot():
    user = current_user()

    if not user:
        return jsonify({"error": "Login required"}), 401

    data = request.get_json(silent=True) or {}
    message = str(data.get("message", "")).strip().lower()

    if not message:
        reply = "Hi! How can I help you with ServiceHub?"
    elif any(word in message for word in ["hello", "hi", "hey"]):
        reply = (
            "Hi! 👋 I can help with booking, provider status, "
            "tracking and reviews."
        )
    elif "book" in message:
        reply = (
            "Choose Plumber, Electrician or Carpenter, select "
            "a nearby professional and click Book now."
        )
    elif "accept" in message:
        reply = (
            "When the professional accepts your request, "
            "the booking status will change to Accepted immediately."
        )
    elif "reject" in message:
        reply = (
            "If a professional rejects your request, "
            "you can choose another nearby professional."
        )
    elif "track" in message or "location" in message:
        reply = (
            "After the professional starts travelling, use the "
            "Track button in My bookings to view their shared location."
        )
    elif any(word in message for word in ["review", "rating", "feedback"]):
        reply = (
            "After the booking is completed, use Rate service "
            "to give a 1–5 star rating and feedback."
        )
    elif "status" in message:
        reply = (
            "Booking statuses are Requested → Accepted → "
            "On the way → Started → Completed."
        )
    else:
        reply = (
            "I can help with booking, acceptance/rejection, "
            "provider status, tracking and reviews."
        )

    return jsonify({"reply": reply})


# --------------------------------------------------
# SOCKET.IO CONNECTION
# --------------------------------------------------

@socketio.on("connect")
def connected(auth=None):
    user = current_user()

    if user:
        join_room(f"user_{user.id}")


# --------------------------------------------------
# LEGACY LOCAL UPLOADS
# New uploads use Supabase public URLs.
# --------------------------------------------------

@app.route("/uploads/<path:path>")
def uploaded(path):
    return send_from_directory(UPLOAD_ROOT, path)


# --------------------------------------------------
# DATABASE INITIALIZATION / SMALL MIGRATIONS
# --------------------------------------------------

with app.app_context():
    db.create_all()

    inspector = inspect(db.engine)

    review_cols = {
        column["name"]
        for column in inspector.get_columns("review")
    }

    if "work_description" not in review_cols:
        with db.engine.begin() as connection:
            connection.execute(
                text(
                    "ALTER TABLE review "
                    "ADD COLUMN work_description TEXT"
                )
            )

    user_cols = {
        column["name"]
        for column in inspect(db.engine).get_columns("user")
    }

    if "phone" not in user_cols:
        with db.engine.begin() as connection:
            connection.execute(
                text(
                    "ALTER TABLE user "
                    "ADD COLUMN phone VARCHAR(30) DEFAULT ''"
                )
            )


# --------------------------------------------------
# RUN APPLICATION
# --------------------------------------------------

if __name__ == "__main__":
    socketio.run(
        app,
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5001)),
        debug=os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    )
