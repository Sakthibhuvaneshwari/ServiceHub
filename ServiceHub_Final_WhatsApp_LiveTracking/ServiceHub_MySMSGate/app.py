        "cancelled": "This booking has been cancelled."
    }
    message = messages.get(status, f"Booking #{booking.id} is now {status.replace('_', ' ')}.")
    create_notification(other_id, "Booking update", message, booking.id)
    socketio.emit("status_update", {"booking_id": booking.id, "status": status, "message": message}, room=f"user_{other_id}")
    wa_url = None
    if user.id == booking.provider_id and status in provider_statuses:
        number = "".join(ch for ch in (booking.customer.phone or "") if ch.isdigit())
        wa_text = f"Hi {booking.customer.name}, {message} Booking #{booking.id} - ServiceHub."
        wa_url = f"https://wa.me/{number}?text={quote(wa_text)}" if number else None
    return jsonify({"ok": True, "status": status, "message": message, "whatsapp_url": wa_url})


@app.route("/api/booking/<int:bid>/location", methods=["POST"])
def update_booking_location(bid):
    user = current_user()
    if not user:
        return jsonify({"error": "Login required"}), 401
    booking = Booking.query.get_or_404(bid)
    if user.id not in (booking.customer_id, booking.provider_id):
        return jsonify({"error": "Unauthorized"}), 403
    data = request.get_json(silent=True) or {}
    try:
        lat, lng = float(data.get("lat")), float(data.get("lng"))
    except (TypeError, ValueError):
        return jsonify({"error": "Valid coordinates are required"}), 400
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        return jsonify({"error": "Invalid coordinates"}), 400
    if user.id == booking.provider_id:
        booking.provider_lat, booking.provider_lng = lat, lng
        target_id, role = booking.customer_id, "provider"
    else:
        booking.customer_lat, booking.customer_lng = lat, lng
        target_id, role = booking.provider_id, "customer"
    db.session.commit()
    socketio.emit("location_update", {
        "booking_id": booking.id, "role": role, "lat": lat, "lng": lng,
        "updated_at": datetime.utcnow().strftime("%d %b %Y %I:%M:%S %p")
    }, room=f"user_{target_id}")
    return jsonify({"success": True, "lat": lat, "lng": lng, "role": role})


@app.route("/api/review", methods=["POST"])
def add_review():
    user = current_user()
    if not user or user.role != "customer":
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    try:
        booking_id, rating = int(data.get("booking_id")), int(data.get("rating", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "Valid booking ID and rating are required"}), 400
    booking = db.session.get(Booking, booking_id)
    if not booking or booking.customer_id != user.id or booking.status != "completed":
        return jsonify({"error": "Review allowed after completion"}), 400
    if Review.query.filter_by(booking_id=booking.id).first():
        return jsonify({"error": "Already reviewed"}), 400
    feedback = str(data.get("feedback", "")).strip()
    work_description = str(data.get("work_description", "")).strip()
    if not 1 <= rating <= 5 or not feedback or not work_description:
        return jsonify({"error": "Rating, work details and feedback are required"}), 400
    review = Review(
        booking_id=booking.id, customer_id=user.id, provider_id=booking.provider_id,
        rating=rating, feedback=feedback, work_description=work_description
    )
    db.session.add(review)
    db.session.commit()
    create_notification(booking.provider_id, "New customer review", f"You received a {review.rating}/5 review from {user.name}.", booking.id)
    socketio.emit("review_notification", {"booking_id": booking.id, "rating": review.rating, "feedback": review.feedback}, room=f"user_{booking.provider_id}")
    return jsonify({"ok": True})


@app.route("/api/chatbot", methods=["POST"])
def chatbot():
    if not current_user():
        return jsonify({"error": "Login required"}), 401
    data = request.get_json(silent=True) or {}
    message = str(data.get("message", "")).strip().lower()
    if not message:
        reply = "Hi! How can I help you with ServiceHub?"
    elif any(word in message for word in ("hello", "hi", "hey")):
        reply = "Hi! 👋 I can help with booking, provider status, tracking and reviews."
    elif "book" in message:
        reply = "Choose Plumber, Electrician or Carpenter, select a nearby professional and click Book now."
    elif "accept" in message:
        reply = "When the professional accepts your request, the booking status changes to Accepted."
    elif "reject" in message:
        reply = "If a professional rejects your request, you can choose another nearby professional."
    elif "track" in message or "location" in message:
        reply = "After the professional starts travelling, use Track in My bookings to view their shared location."
    elif any(word in message for word in ("review", "rating", "feedback")):
        reply = "After the booking is completed, use Rate service to give a 1–5 star rating and feedback."
    elif "status" in message:
        reply = "Booking statuses are Requested → Accepted → On the way → Started → Completed."
    else:
        reply = "I can help with booking, provider status, tracking and reviews."
    return jsonify({"reply": reply})


@socketio.on("connect")
def connected(auth=None):
    user = current_user()
    if user:
        join_room(f"user_{user.id}")


with app.app_context():
    db.create_all()
    from sqlalchemy import inspect, text
    inspector = inspect(db.engine)
    tables = set(inspector.get_table_names())

    if "review" in tables:
        review_cols = {c["name"] for c in inspector.get_columns("review")}
        if "work_description" not in review_cols:
            with db.engine.begin() as conn:
                conn.execute(text("ALTER TABLE review ADD COLUMN work_description TEXT"))

    if "user" in tables:
        user_cols = {c["name"] for c in inspector.get_columns("user")}
        if "phone" not in user_cols:
            with db.engine.begin() as conn:
                conn.execute(text("ALTER TABLE user ADD COLUMN phone VARCHAR(30) DEFAULT ''"))


if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 5001)), debug=False)
