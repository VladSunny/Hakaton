from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    session,
    jsonify,
)
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager,
    UserMixin,
    login_user,
    logout_user,
    login_required,
    current_user,
)
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from functools import wraps
import os

app = Flask(__name__)
app.config["SECRET_KEY"] = "your-secret-key-here-change-in-production"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///school_food.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message = "Пожалуйста, войдите в систему"

# ============ MODELS ============


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="student")
    student_class = db.Column(db.String(10))
    balance = db.Column(db.Float, default=0.0)
    allergies = db.Column(db.String(500), default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    orders = db.relationship("Order", backref="user", lazy=True)
    reviews = db.relationship("Review", backref="user", lazy=True)
    notifications = db.relationship("Notification", backref="user", lazy=True)


class MenuItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    meal_type = db.Column(db.String(20), nullable=False)  # breakfast/lunch
    price = db.Column(db.Float, nullable=False)
    calories = db.Column(db.Integer)
    allergens = db.Column(db.String(200), default="")
    image = db.Column(db.String(10), default="🍽️")
    available = db.Column(db.Boolean, default=True)

    reviews = db.relationship("Review", backref="menu_item", lazy=True)


class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    total = db.Column(db.Float, nullable=False)
    meal_type = db.Column(db.String(20), nullable=False)
    status = db.Column(db.String(20), default="pending")  # pending/received
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    items = db.relationship("OrderItem", backref="order", lazy=True)


class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("order.id"), nullable=False)
    menu_item_id = db.Column(db.Integer, db.ForeignKey("menu_item.id"), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    price = db.Column(db.Float, nullable=False)

    menu_item = db.relationship("MenuItem")


class Review(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    menu_item_id = db.Column(db.Integer, db.ForeignKey("menu_item.id"), nullable=False)
    rating = db.Column(db.Integer, nullable=False)
    text = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    unit = db.Column(db.String(20), nullable=False)
    quantity = db.Column(db.Float, nullable=False)
    min_quantity = db.Column(db.Float, nullable=False)


class PurchaseRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False)
    quantity = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(20), default="pending")  # pending/approved/rejected
    created_by = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    product = db.relationship("Product")


class Subscription(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    sub_type = db.Column(db.String(20), nullable=False)  # week/month
    remaining_meals = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship("User")


class Notification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    text = db.Column(db.String(500), nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class ServedMeals(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False, default=datetime.utcnow().date)
    breakfast_count = db.Column(db.Integer, default=0)
    lunch_count = db.Column(db.Integer, default=0)


# ============ DECORATORS ============


def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for("login"))
            if current_user.role not in roles:
                flash("У вас нет доступа к этой странице", "error")
                return redirect(url_for("index"))
            return f(*args, **kwargs)

        return decorated_function

    return decorator


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# ============ AUTH ROUTES ============


@app.route("/")
def index():
    if current_user.is_authenticated:
        if current_user.role == "student":
            return redirect(url_for("student_menu"))
        elif current_user.role == "cook":
            return redirect(url_for("cook_serve"))
        elif current_user.role == "admin":
            return redirect(url_for("admin_dashboard"))
    return render_template("index.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        user = User.query.filter_by(email=email).first()

        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            flash(f"Добро пожаловать, {user.name}!", "success")
            return redirect(url_for("index"))
        flash("Неверный email или пароль", "error")

    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    if request.method == "POST":
        email = request.form.get("email")
        name = request.form.get("name")
        password = request.form.get("password")
        student_class = request.form.get("student_class")

        if User.query.filter_by(email=email).first():
            flash("Пользователь с таким email уже существует", "error")
            return redirect(url_for("register"))

        user = User(
            email=email,
            name=name,
            password_hash=generate_password_hash(password),
            student_class=student_class,
            role="student",
        )
        db.session.add(user)
        db.session.commit()

        # Welcome notification
        notification = Notification(
            user_id=user.id, text="Добро пожаловать в систему школьного питания!"
        )
        db.session.add(notification)
        db.session.commit()

        flash("Регистрация успешна! Войдите в систему.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Вы вышли из системы", "info")
    return redirect(url_for("login"))


# ============ STUDENT ROUTES ============


@app.route("/student/menu")
@login_required
@role_required("student")
def student_menu():
    breakfast = MenuItem.query.filter_by(meal_type="breakfast", available=True).all()
    lunch = MenuItem.query.filter_by(meal_type="lunch", available=True).all()
    user_allergies = current_user.allergies.split(",") if current_user.allergies else []
    return render_template(
        "student/menu.html",
        breakfast=breakfast,
        lunch=lunch,
        user_allergies=user_allergies,
    )


@app.route("/student/orders")
@login_required
@role_required("student")
def student_orders():
    orders = (
        Order.query.filter_by(user_id=current_user.id)
        .order_by(Order.created_at.desc())
        .all()
    )
    return render_template("student/orders.html", orders=orders)


@app.route("/student/payment")
@login_required
@role_required("student")
def student_payment():
    subscription = Subscription.query.filter_by(user_id=current_user.id).first()
    return render_template("student/payment.html", subscription=subscription)


@app.route("/student/profile")
@login_required
@role_required("student")
def student_profile():
    all_allergens = ["глютен", "молоко", "яйца", "орехи", "рыба", "соя", "арахис"]
    user_allergies = current_user.allergies.split(",") if current_user.allergies else []
    orders_count = Order.query.filter_by(user_id=current_user.id).count()
    return render_template(
        "student/profile.html",
        all_allergens=all_allergens,
        user_allergies=user_allergies,
        orders_count=orders_count,
    )


@app.route("/api/cart/checkout", methods=["POST"])
@login_required
@role_required("student")
def checkout():
    data = request.json
    items = data.get("items", [])
    total = sum(item["price"] for item in items)

    if current_user.balance < total:
        return jsonify({"success": False, "message": "Недостаточно средств на балансе"})

    # Create order
    order = Order(
        user_id=current_user.id,
        total=total,
        meal_type=items[0]["type"] if items else "lunch",
        status="pending",
    )
    db.session.add(order)
    db.session.flush()

    # Add order items
    for item in items:
        order_item = OrderItem(
            order_id=order.id,
            menu_item_id=item["id"],
            name=item["name"],
            price=item["price"],
        )
        db.session.add(order_item)

    # Deduct balance
    current_user.balance -= total
    db.session.commit()

    return jsonify(
        {
            "success": True,
            "message": "Заказ успешно оформлен!",
            "new_balance": current_user.balance,
        }
    )


@app.route("/api/topup", methods=["POST"])
@login_required
@role_required("student")
def topup():
    data = request.json
    amount = data.get("amount", 0)

    if amount <= 0:
        return jsonify({"success": False, "message": "Неверная сумма"})

    current_user.balance += amount
    db.session.commit()

    return jsonify(
        {
            "success": True,
            "message": f"Баланс пополнен на {amount} ₽",
            "new_balance": current_user.balance,
        }
    )


@app.route("/api/subscription", methods=["POST"])
@login_required
@role_required("student")
def buy_subscription():
    data = request.json
    sub_type = data.get("type")
    prices = {"week": 1500, "month": 5500}
    meals = {"week": 10, "month": 40}

    price = prices.get(sub_type, 0)

    if current_user.balance < price:
        return jsonify({"success": False, "message": "Недостаточно средств"})

    current_user.balance -= price

    # Remove old subscription if exists
    Subscription.query.filter_by(user_id=current_user.id).delete()

    subscription = Subscription(
        user_id=current_user.id, sub_type=sub_type, remaining_meals=meals[sub_type]
    )
    db.session.add(subscription)
    db.session.commit()

    return jsonify({"success": True, "message": "Абонемент активирован!"})


@app.route("/api/allergies", methods=["POST"])
@login_required
@role_required("student")
def update_allergies():
    data = request.json
    allergies = data.get("allergies", [])
    current_user.allergies = ",".join(allergies)
    db.session.commit()
    return jsonify({"success": True})


@app.route("/api/review", methods=["POST"])
@login_required
@role_required("student")
def add_review():
    data = request.json
    review = Review(
        user_id=current_user.id,
        menu_item_id=data["menu_item_id"],
        rating=data["rating"],
        text=data.get("text", ""),
    )
    db.session.add(review)
    db.session.commit()
    return jsonify({"success": True, "message": "Отзыв добавлен!"})


@app.route("/api/order/<int:order_id>/receive", methods=["POST"])
@login_required
@role_required("student")
def mark_order_received(order_id):
    order = Order.query.get_or_404(order_id)
    if order.user_id != current_user.id:
        return jsonify({"success": False, "message": "Доступ запрещён"})
    order.status = "received"
    db.session.commit()
    return jsonify({"success": True})


# ============ COOK ROUTES ============


@app.route("/cook/serve")
@login_required
@role_required("cook")
def cook_serve():
    today = datetime.utcnow().date()
    now = datetime.utcnow()
    served = ServedMeals.query.filter_by(date=today).first()
    if not served:
        served = ServedMeals(date=today)
        db.session.add(served)
        db.session.commit()

    pending_orders = (
        Order.query.filter_by(status="pending").order_by(Order.created_at.desc()).all()
    )
    return render_template(
        "cook/serve.html", served=served, pending_orders=pending_orders, now=now
    )


@app.route("/cook/inventory")
@login_required
@role_required("cook")
def cook_inventory():
    products = Product.query.all()
    # Подсчитываем количество продуктов с низким запасом
    low_count = sum(1 for p in products if p.quantity <= p.min_quantity)
    return render_template(
        "cook/inventory.html", products=products, low_count=low_count
    )


@app.route("/cook/purchase")
@login_required
@role_required("cook")
def cook_purchase():
    requests = PurchaseRequest.query.order_by(PurchaseRequest.created_at.desc()).all()
    products = Product.query.all()
    return render_template("cook/purchase.html", requests=requests, products=products)


@app.route("/api/serve/<meal_type>", methods=["POST"])
@login_required
@role_required("cook")
def serve_meal(meal_type):
    data = request.json
    count = data.get("count", 1)

    today = datetime.utcnow().date()
    served = ServedMeals.query.filter_by(date=today).first()
    if not served:
        served = ServedMeals(date=today)
        db.session.add(served)

    if meal_type == "breakfast":
        served.breakfast_count = max(0, served.breakfast_count + count)
    else:
        served.lunch_count = max(0, served.lunch_count + count)

    db.session.commit()
    return jsonify(
        {
            "success": True,
            "breakfast": served.breakfast_count,
            "lunch": served.lunch_count,
        }
    )


@app.route("/api/order/<int:order_id>/confirm", methods=["POST"])
@login_required
@role_required("cook")
def confirm_order(order_id):
    order = Order.query.get_or_404(order_id)
    order.status = "received"

    # Update served count
    today = datetime.utcnow().date()
    served = ServedMeals.query.filter_by(date=today).first()
    if served:
        if order.meal_type == "breakfast":
            served.breakfast_count += 1
        else:
            served.lunch_count += 1

    db.session.commit()
    return jsonify({"success": True})


@app.route("/api/product/<int:product_id>/update", methods=["POST"])
@login_required
@role_required("cook")
def update_product(product_id):
    data = request.json
    product = Product.query.get_or_404(product_id)
    product.quantity = data.get("quantity", product.quantity)
    db.session.commit()
    return jsonify({"success": True})


@app.route("/api/purchase-request", methods=["POST"])
@login_required
@role_required("cook")
def create_purchase_request():
    data = request.json
    product = Product.query.get_or_404(data["product_id"])

    pr = PurchaseRequest(
        product_id=data["product_id"],
        quantity=data["quantity"],
        created_by=current_user.name,
    )
    db.session.add(pr)
    db.session.commit()
    return jsonify({"success": True, "message": "Заявка создана"})


# ============ ADMIN ROUTES ============


@app.route("/admin/dashboard")
@login_required
@role_required("admin")
def admin_dashboard():
    from sqlalchemy import func
    from datetime import timedelta

    today = datetime.utcnow().date()
    yesterday = today - timedelta(days=1)
    week_ago = today - timedelta(days=7)

    # Basic stats
    total_orders = Order.query.count()
    today_orders = Order.query.filter(db.func.date(Order.created_at) == today).count()
    yesterday_orders = Order.query.filter(
        db.func.date(Order.created_at) == yesterday
    ).count()
    total_revenue = db.session.query(db.func.sum(Order.total)).scalar() or 0
    students_count = User.query.filter_by(role="student").count()
    pending_requests = PurchaseRequest.query.filter_by(status="pending").count()

    # Orders change percentage
    orders_change = 0
    if yesterday_orders > 0:
        orders_change = int(
            ((today_orders - yesterday_orders) / yesterday_orders) * 100
        )

    # Breakfast and lunch counts
    breakfast_count = Order.query.filter_by(meal_type="breakfast").count()
    lunch_count = Order.query.filter_by(meal_type="lunch").count()

    # Subscriptions count
    subscriptions_count = Subscription.query.count()

    # Average rating
    avg_rating = db.session.query(func.avg(Review.rating)).scalar() or 0

    # Weekly orders for chart
    weekly_orders = []
    for i in range(6, -1, -1):
        day = today - timedelta(days=i)
        count = Order.query.filter(db.func.date(Order.created_at) == day).count()
        weekly_orders.append(
            {
                "day": ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"][day.weekday()],
                "count": count,
            }
        )

    max_weekly = max([d["count"] for d in weekly_orders]) if weekly_orders else 1

    # Popular dishes
    popular = (
        db.session.query(OrderItem.name, func.count(OrderItem.id).label("count"))
        .group_by(OrderItem.name)
        .order_by(func.count(OrderItem.id).desc())
        .limit(5)
        .all()
    )

    max_popular = popular[0][1] if popular else 1

    # Recent orders
    recent_orders = Order.query.order_by(Order.created_at.desc()).limit(5).all()

    return render_template(
        "admin/dashboard.html",
        total_orders=total_orders,
        today_orders=today_orders,
        orders_change=orders_change,
        total_revenue=total_revenue,
        students_count=students_count,
        pending_requests=pending_requests,
        recent_orders=recent_orders,
        breakfast_count=breakfast_count,
        lunch_count=lunch_count,
        subscriptions_count=subscriptions_count,
        avg_rating=round(avg_rating, 1),
        weekly_orders=weekly_orders,
        max_weekly=max_weekly if max_weekly > 0 else 1,
        popular=popular,
        max_popular=max_popular if max_popular > 0 else 1,
        now=datetime.utcnow(),
    )


@app.route("/admin/global_menu")
@login_required
@role_required("admin")
def global_menu():
    from sqlalchemy import func
    from datetime import timedelta

    today = datetime.utcnow().date()
    yesterday = today - timedelta(days=1)
    week_ago = today - timedelta(days=7)

    # Basic stats
    total_orders = Order.query.count()
    today_orders = Order.query.filter(db.func.date(Order.created_at) == today).count()
    yesterday_orders = Order.query.filter(
        db.func.date(Order.created_at) == yesterday
    ).count()
    total_revenue = db.session.query(db.func.sum(Order.total)).scalar() or 0
    students_count = User.query.filter_by(role="student").count()
    pending_requests = PurchaseRequest.query.filter_by(status="pending").count()

    # Orders change percentage
    orders_change = 0
    if yesterday_orders > 0:
        orders_change = int(
            ((today_orders - yesterday_orders) / yesterday_orders) * 100
        )

    # Breakfast and lunch counts
    breakfast_count = Order.query.filter_by(meal_type="breakfast").count()
    lunch_count = Order.query.filter_by(meal_type="lunch").count()

    # Subscriptions count
    subscriptions_count = Subscription.query.count()

    # Average rating
    avg_rating = db.session.query(func.avg(Review.rating)).scalar() or 0

    # Weekly orders for chart
    weekly_orders = []
    for i in range(6, -1, -1):
        day = today - timedelta(days=i)
        count = Order.query.filter(db.func.date(Order.created_at) == day).count()
        weekly_orders.append(
            {
                "day": ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"][day.weekday()],
                "count": count,
            }
        )

    max_weekly = max([d["count"] for d in weekly_orders]) if weekly_orders else 1

    # Popular dishes
    popular = (
        db.session.query(OrderItem.name, func.count(OrderItem.id).label("count"))
        .group_by(OrderItem.name)
        .order_by(func.count(OrderItem.id).desc())
        .limit(5)
        .all()
    )

    max_popular = popular[0][1] if popular else 1

    # Recent orders
    recent_orders = Order.query.order_by(Order.created_at.desc()).limit(5).all()

    return render_template(
        "admin/global_menu.html",
        total_orders=total_orders,
        today_orders=today_orders,
        orders_change=orders_change,
        total_revenue=total_revenue,
        students_count=students_count,
        pending_requests=pending_requests,
        recent_orders=recent_orders,
        breakfast_count=breakfast_count,
        lunch_count=lunch_count,
        subscriptions_count=subscriptions_count,
        avg_rating=round(avg_rating, 1),
        weekly_orders=weekly_orders,
        max_weekly=max_weekly if max_weekly > 0 else 1,
        popular=popular,
        max_popular=max_popular if max_popular > 0 else 1,
        now=datetime.utcnow(),
    )


@app.route("/admin/requests")
@login_required
@role_required("admin")
def admin_requests():
    requests = (
        PurchaseRequest.query.filter_by(status="pending")
        .order_by(PurchaseRequest.created_at.desc())
        .all()
    )
    return render_template("admin/requests.html", requests=requests)


@app.route("/admin/reports")
@login_required
@role_required("admin")
def admin_reports():
    from sqlalchemy import func
    from datetime import timedelta

    today = datetime.utcnow().date()
    week_ago = today - timedelta(days=7)
    month_ago = today - timedelta(days=30)

    # All orders
    orders = Order.query.all()
    orders_count = len(orders)

    # Revenue calculations
    total_revenue = db.session.query(func.sum(Order.total)).scalar() or 0
    week_revenue = (
        db.session.query(func.sum(Order.total))
        .filter(db.func.date(Order.created_at) >= week_ago)
        .scalar()
        or 0
    )
    month_revenue = (
        db.session.query(func.sum(Order.total))
        .filter(db.func.date(Order.created_at) >= month_ago)
        .scalar()
        or 0
    )

    # Meal type counts
    breakfast_count = Order.query.filter_by(meal_type="breakfast").count()
    lunch_count = Order.query.filter_by(meal_type="lunch").count()
    total_meals = breakfast_count + lunch_count

    # Average check
    avg_check = total_revenue / orders_count if orders_count > 0 else 0

    # Items per order
    total_items = db.session.query(func.count(OrderItem.id)).scalar() or 0
    items_per_order = total_items / orders_count if orders_count > 0 else 0

    # Breakfast revenue (approximate based on average breakfast price)
    breakfast_revenue = (
        db.session.query(func.sum(Order.total))
        .filter_by(meal_type="breakfast")
        .scalar()
        or 0
    )
    lunch_revenue = (
        db.session.query(func.sum(Order.total)).filter_by(meal_type="lunch").scalar()
        or 0
    )

    # Average prices
    avg_breakfast_price = (
        breakfast_revenue / breakfast_count if breakfast_count > 0 else 0
    )
    avg_lunch_price = lunch_revenue / lunch_count if lunch_count > 0 else 0

    # Recent orders with user info
    recent_orders = Order.query.order_by(Order.created_at.desc()).limit(10).all()

    # Orders received vs pending
    received_count = Order.query.filter_by(status="received").count()
    pending_count = Order.query.filter_by(status="pending").count()

    return render_template(
        "admin/reports.html",
        total_revenue=total_revenue,
        week_revenue=week_revenue,
        month_revenue=month_revenue,
        breakfast_count=breakfast_count,
        lunch_count=lunch_count,
        total_meals=total_meals,
        avg_check=avg_check,
        items_per_order=round(items_per_order, 1),
        breakfast_revenue=breakfast_revenue,
        lunch_revenue=lunch_revenue,
        avg_breakfast_price=round(avg_breakfast_price, 0),
        avg_lunch_price=round(avg_lunch_price, 0),
        recent_orders=recent_orders,
        orders_count=orders_count,
        received_count=received_count,
        pending_count=pending_count,
    )


@app.route("/admin/users")
@login_required
@role_required("admin")
def admin_users():
    users = User.query.all()
    return render_template("admin/users.html", users=users)


@app.route("/api/request/<int:request_id>/<action>", methods=["POST"])
@login_required
@role_required("admin")
def handle_request(request_id, action):
    pr = PurchaseRequest.query.get_or_404(request_id)

    if action == "approve":
        pr.status = "approved"
        # Add to inventory
        pr.product.quantity += pr.quantity
        message = "Заявка одобрена"
    else:
        pr.status = "rejected"
        message = "Заявка отклонена"

    db.session.commit()
    return jsonify({"success": True, "message": message})


# ============ ADMIN USER MANAGEMENT ============


@app.route("/api/admin/user/create", methods=["POST"])
@login_required
@role_required("admin")
def admin_create_user():
    data = request.json

    # Check if email already exists
    if User.query.filter_by(email=data["email"]).first():
        return jsonify(
            {"success": False, "message": "Пользователь с таким email уже существует"}
        )

    user = User(
        email=data["email"],
        name=data["name"],
        password_hash=generate_password_hash(data["password"]),
        role=data["role"],
        student_class=data.get("student_class", ""),
        balance=float(data.get("balance", 0)) if data["role"] == "student" else 0,
    )
    db.session.add(user)
    db.session.commit()

    return jsonify({"success": True, "message": "Пользователь создан"})


@app.route("/api/admin/user/<int:user_id>/update", methods=["POST"])
@login_required
@role_required("admin")
def admin_update_user(user_id):
    data = request.json
    user = User.query.get_or_404(user_id)

    # Check if email is taken by another user
    existing = User.query.filter_by(email=data["email"]).first()
    if existing and existing.id != user_id:
        return jsonify({"success": False, "message": "Этот email уже используется"})

    user.name = data["name"]
    user.email = data["email"]
    user.role = data["role"]
    user.student_class = data.get("student_class", "")

    if data["role"] == "student":
        user.balance = float(data.get("balance", 0))

    # Update password if provided
    if data.get("password"):
        user.password_hash = generate_password_hash(data["password"])

    db.session.commit()
    return jsonify({"success": True, "message": "Данные пользователя обновлены"})


@app.route("/api/admin/user/<int:user_id>/delete", methods=["POST"])
@login_required
@role_required("admin")
def admin_delete_user(user_id):
    user = User.query.get_or_404(user_id)

    # Prevent deleting yourself
    if user.id == current_user.id:
        return jsonify({"success": False, "message": "Нельзя удалить свой аккаунт"})

    # Delete related data
    Order.query.filter_by(user_id=user_id).delete()
    Review.query.filter_by(user_id=user_id).delete()
    Notification.query.filter_by(user_id=user_id).delete()
    Subscription.query.filter_by(user_id=user_id).delete()

    db.session.delete(user)
    db.session.commit()

    return jsonify({"success": True, "message": "Пользователь удалён"})


# ============ PROFILE UPDATE ============


@app.route("/api/profile/update", methods=["POST"])
@login_required
def update_profile():
    data = request.json

    # Check if email is taken by another user
    existing = User.query.filter_by(email=data["email"]).first()
    if existing and existing.id != current_user.id:
        return jsonify({"success": False, "message": "Этот email уже используется"})

    current_user.name = data["name"]
    current_user.email = data["email"]

    if current_user.role == "student" and data.get("student_class"):
        current_user.student_class = data["student_class"]

    # Update password if provided
    if data.get("password"):
        current_user.password_hash = generate_password_hash(data["password"])

    db.session.commit()
    return jsonify({"success": True, "message": "Профиль обновлён"})


# ============ NOTIFICATIONS ============


@app.route("/api/notifications")
@login_required
def get_notifications():
    notifications = (
        Notification.query.filter_by(user_id=current_user.id)
        .order_by(Notification.created_at.desc())
        .limit(10)
        .all()
    )
    unread_count = Notification.query.filter_by(
        user_id=current_user.id, is_read=False
    ).count()

    return jsonify(
        {
            "notifications": [
                {
                    "id": n.id,
                    "text": n.text,
                    "is_read": n.is_read,
                    "date": n.created_at.strftime("%d.%m.%Y %H:%M"),
                }
                for n in notifications
            ],
            "unread_count": unread_count,
        }
    )


@app.route("/api/notifications/read", methods=["POST"])
@login_required
def mark_notifications_read():
    Notification.query.filter_by(user_id=current_user.id).update({"is_read": True})
    db.session.commit()
    return jsonify({"success": True})


# ============ INIT DATABASE ============


def init_db():
    with app.app_context():
        db.create_all()

        # Check if data exists
        if User.query.first() is None:
            # Create test users
            users = [
                User(
                    email="student@school.ru",
                    password_hash=generate_password_hash("123456"),
                    name="Петров Алексей",
                    role="student",
                    student_class="9А",
                    balance=1500,
                ),
                User(
                    email="cook@school.ru",
                    password_hash=generate_password_hash("123456"),
                    name="Сидорова Мария",
                    role="cook",
                ),
                User(
                    email="admin@school.ru",
                    password_hash=generate_password_hash("123456"),
                    name="Иванов Сергей",
                    role="admin",
                ),
            ]
            db.session.add_all(users)

            # Create menu items
            menu_items = [
                MenuItem(
                    name="Каша овсяная с фруктами",
                    meal_type="breakfast",
                    price=80,
                    calories=250,
                    allergens="глютен,молоко",
                    image="🥣",
                ),
                MenuItem(
                    name="Омлет с сыром",
                    meal_type="breakfast",
                    price=95,
                    calories=320,
                    allergens="яйца,молоко",
                    image="🍳",
                ),
                MenuItem(
                    name="Блинчики с творогом",
                    meal_type="breakfast",
                    price=110,
                    calories=380,
                    allergens="глютен,молоко,яйца",
                    image="🥞",
                ),
                MenuItem(
                    name="Йогурт с мюсли",
                    meal_type="breakfast",
                    price=75,
                    calories=200,
                    allergens="молоко,глютен",
                    image="🥛",
                ),
                MenuItem(
                    name="Борщ украинский",
                    meal_type="lunch",
                    price=120,
                    calories=280,
                    allergens="",
                    image="🍲",
                ),
                MenuItem(
                    name="Котлета куриная с пюре",
                    meal_type="lunch",
                    price=150,
                    calories=450,
                    allergens="глютен,яйца",
                    image="🍖",
                ),
                MenuItem(
                    name="Рыба запеченная с овощами",
                    meal_type="lunch",
                    price=180,
                    calories=380,
                    allergens="рыба",
                    image="🐟",
                ),
                MenuItem(
                    name="Макароны с сыром",
                    meal_type="lunch",
                    price=100,
                    calories=420,
                    allergens="глютен,молоко",
                    image="🍝",
                ),
                MenuItem(
                    name="Салат овощной",
                    meal_type="lunch",
                    price=70,
                    calories=120,
                    allergens="",
                    image="🥗",
                ),
                MenuItem(
                    name="Компот из сухофруктов",
                    meal_type="lunch",
                    price=30,
                    calories=80,
                    allergens="",
                    image="🍹",
                ),
            ]
            db.session.add_all(menu_items)

            # Create products
            products = [
                Product(name="Молоко", unit="л", quantity=50, min_quantity=20),
                Product(name="Яйца", unit="шт", quantity=200, min_quantity=100),
                Product(name="Мука", unit="кг", quantity=30, min_quantity=15),
                Product(name="Сахар", unit="кг", quantity=25, min_quantity=10),
                Product(name="Масло сливочное", unit="кг", quantity=10, min_quantity=5),
                Product(name="Курица", unit="кг", quantity=40, min_quantity=20),
                Product(name="Картофель", unit="кг", quantity=100, min_quantity=50),
                Product(name="Морковь", unit="кг", quantity=30, min_quantity=15),
                Product(name="Рыба", unit="кг", quantity=15, min_quantity=10),
                Product(name="Макароны", unit="кг", quantity=20, min_quantity=10),
            ]
            db.session.add_all(products)

            db.session.commit()
            print("Database initialized with test data!")


if __name__ == "__main__":
    init_db()
    app.run(debug=True)
