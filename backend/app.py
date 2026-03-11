from flask import Flask, render_template, request, redirect, url_for, session
import os
import csv
import random
import hashlib

app = Flask(_name_)
app.secret_key = "supersecretkey"

CRED_FILE = "credentials.csv"

# Password Hash Function
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()


# Home Page
@app.route("/")
def home():
    return render_template("login.html")



# Signup
@app.route("/signup", methods=["GET", "POST"])
def signup():

    if request.method == "POST":

        username = request.form.get("username")
        email = request.form.get("email")
        password = request.form.get("password")

        if not username or not email or not password:
            return "All fields are required"

        # create file if not exists
        if not os.path.exists(CRED_FILE):
            with open(CRED_FILE, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["id", "username", "email", "password"])

        # read existing users
        existing_ids = set()

        with open(CRED_FILE, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                existing_ids.add(row["id"])

        # generate unique user id
        while True:
            uid = "U" + str(random.randint(1000, 9999))
            if uid not in existing_ids:
                break

        # save user
        with open(CRED_FILE, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([uid, username.lower(), email, hash_password(password)])

        session["user_id"] = uid

        return redirect(url_for("dashboard"))

    return render_template("signup.html")



# Login
@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        username = request.form.get("username")
        password = request.form.get("password")

        if not os.path.exists(CRED_FILE):
            return "No users registered"

        with open(CRED_FILE, "r") as f:
            reader = csv.DictReader(f)

            for row in reader:
                if row["username"] == username.lower() and row["password"] == hash_password(password):

                    session["user_id"] = row["id"]

                    return redirect(url_for("dashboard"))

        return "Invalid username or password"

    return render_template("login.html")



# Dashboard
@app.route("/dashboard")
def dashboard():

    if "user_id" not in session:
        return redirect(url_for("login"))

    return f"Welcome {session['user_id']} 🚦 Traffic System Dashboard"



# Logout
@app.route("/logout")
def logout():

    session.clear()

    return redirect(url_for("login"))



# Run Server
if _name_ == "_main_":
    app.run(debug=True)