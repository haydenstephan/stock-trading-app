import os

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached


@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    user_id = session.get("user_id")
    current_cash = db.execute("SELECT cash FROM users WHERE id = :id", id=user_id)[0]['cash']
    stocks = db.execute("SELECT stock FROM portfolio WHERE id = :id", id=user_id)
    shares = []
    for i in range(len(stocks)):
        stock = stocks[i]['stock']
        share = db.execute("SELECT shares FROM portfolio WHERE id = :id AND stock = :stock", id=user_id, stock=stock)[0]['shares']
        stock_price = lookup(stock)['price']
        holding_value = share * stock_price
        shares.append([stock, share, usd(stock_price), usd(holding_value)])
    total_holdings = 0
    for e in shares:
        total_holdings = total_holdings + float(e[3].strip("$").replace(",", ""))
    total_cash = total_holdings + current_cash
    current_cash = usd(current_cash)
    total_cash = usd(total_cash)
    return render_template("index.html", shares=shares, current_cash=current_cash, total_cash=total_cash)


@app.route("/deposit", methods=["GET", "POST"])
@login_required
def deposit():
    if request.method == "GET":
        return render_template("deposit.html")
    if request.method == "POST":
        user_id = session.get("user_id")
        dollars = request.form.get("dollars")
        cents = request.form.get("cents")
        if not dollars.isdigit() or not cents.isdigit() or int(cents) > 99:
            return apology("invalid input")
        deposit = float(dollars) + (float(cents) * .01)
        db.execute("UPDATE users SET cash = cash + :deposit WHERE id = :id", deposit=deposit, id=user_id)
        return redirect("/")


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    if request.method == "GET":
        return render_template("buy.html")
    if request.method == "POST":
        symbol = request.form.get("symbol").upper()
        number = request.form.get("shares")
        if symbol == "":
            return apology("please input stock symbol")
        if request.form.get("number") == "":
            return apology("please input number of shares")
        if not request.form.get("shares").isdigit():
            return apology("please input an integer into the number of shares field")
        stock = lookup(symbol)
        if stock == None:
            return apology("Stock not found")
        user_id = session.get("user_id")
        cash = db.execute("SELECT cash FROM users WHERE id = :id", id=user_id)[0]['cash']
        price = float(number) * stock["price"]
        if cash < price:
            return apology("NOT ENOUGH CASH")
        else:
            db.execute("UPDATE users SET cash = cash - :price WHERE id = :id", price=price, id=user_id)
            db.execute("INSERT INTO history (id, stock, shares, price, time, type) VALUES(:id, :stock, :shares, :price, CURRENT_TIMESTAMP, :type)",
                       id=user_id, stock=symbol, shares=number, price=price, type="BOUGHT")
            if db.execute("SELECT * FROM portfolio WHERE id = :id AND stock =:stock", id=user_id, stock=symbol):
                db.execute("UPDATE portfolio SET shares= shares + :shares WHERE id =:id AND stock = :stock",
                           shares=number, id=user_id, stock=symbol)
                return redirect("/")
            else:
                db.execute("INSERT INTO portfolio (id, stock, shares) VALUES(:id, :stock, :shares)",
                           id=user_id, stock=symbol, shares=number)
                return redirect("/")


@app.route("/check", methods=["GET"])
def check():
    """Return true if username available, else false, in JSON format"""
    username = request.args.get("username")
    if not db.execute("SELECT * FROM users WHERE username = :username", username=username):
        return jsonify(True)
    return jsonify(False)


@app.route("/history")
@login_required
def history():
    user_id = session.get("user_id")
    history = db.execute("SELECT * FROM history WHERE id = :id", id=user_id)
    for e in history:
        e['price'] = usd(abs(e['price']))
    return render_template("history.html", history=history)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "GET":
        return render_template("quote.html")
    else:
        quote = lookup(request.form.get("symbol"))
        if not quote:
            return apology("stock does not exist")
        name = quote['name']
        price = usd(quote['price'])
        symbol = quote['symbol']
        return render_template("quoted.html", name=name, price=price, symbol=symbol)


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "GET":
        return render_template("register.html")
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        confirmation = request.form.get("confirmation")
        if username == "":
            return apology("please provide a username")
        if password == "" or confirmation == "":
            return apology("please provide a password and confirmation")
        if password != confirmation:
            return apology("password and confirmation do not match")
        if db.execute("SELECT * FROM users WHERE username = :username", username=username):
            return apology("username already taken")
        hash = generate_password_hash(password)
        db.execute("INSERT INTO users (username, hash) VALUES(:username, :hash)", username=request.form.get("username"), hash=hash)
        session["user_id"] = db.execute("SELECT * FROM users WHERE username = :username",
                                        username=request.form.get("username"))[0]["id"]
        return redirect("/")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    if request.method == "GET":
        user_id = session.get("user_id")
        stock_list = db.execute("SELECT stock FROM portfolio WHERE id = :id", id=user_id)
        stocks = []
        for e in stock_list:
            stocks.append(e['stock'])
        return render_template("sell.html", stocks=stocks)
    """Sell shares of stock"""
    if request.method == "POST":
        user_id = session.get("user_id")
        symbol = request.form.get("symbol")
        shares = request.form.get("shares")
        if not symbol or not shares:
            return apology("please provide stock symbol and shares")
        if shares == "0" or not shares.isdigit():
            return apology("shares must be a positive integer")
        shares_held = db.execute("SELECT shares FROM portfolio WHERE id = :id AND stock = :stock",
                                 id=user_id, stock=symbol)[0]['shares']
        shares = int(shares)
        if shares > shares_held:
            return apology("not enough shares owned")
        selling_price = lookup(symbol)['price']
        total_sell = selling_price * shares
        db.execute("UPDATE users SET cash = cash + :cash WHERE id = :id", cash=total_sell, id=user_id)
        db.execute("INSERT INTO history (id, stock, shares, price, time, type) VALUES(:id, :stock, :shares, :price, CURRENT_TIMESTAMP, :type)",
                   id=user_id, stock=symbol, shares=shares, price=(-1 * total_sell), type="SOLD")
        if shares == shares_held:
            db.execute("DELETE FROM portfolio WHERE id = :id AND stock = :stock", id=user_id, stock=symbol)
        if shares < shares_held:
            db.execute("UPDATE portfolio SET shares = shares - :shares WHERE id = :id AND stock = :stock",
                       shares=shares, id=user_id, stock=symbol)
        return redirect("/")


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
