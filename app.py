from flask import Flask, request, redirect, render_template
import os


app = Flask(
    __name__,
    template_folder="fronted/templates",
    static_folder="fronted/static"
)

# HOME
@app.route('/')
def home():
    return render_template("index.html")

# LOGIN PAGE
@app.route('/login')
def login_page():
    return render_template("login.html")

# SIGNUP PAGE
@app.route('/signup')
def signup_page():
    return render_template("signup.html")


# ================= SIGNUP =================
@app.route('/signup', methods=['POST'])
def signup():
    username = request.form['username']
    email = request.form['email']
    password = request.form['password']

    if not os.path.exists("cred.csv"):
        open("cred.csv", "w").close()

    with open("cred.csv", "r") as f:
        users = f.readlines()

    for user in users:
        data = user.strip().split(",")
        if len(data) == 3:
            u, e, p = data
            if u == username:
                return render_template("signup.html", message="User already exists ❌")

    # save user
    with open("cred.csv", "a") as f:
        f.write(f"{username},{email},{password}\n")

    # 🚀 DIRECT DASHBOARD REDIRECT
    return redirect("/dashboard")

# ================= LOGIN =================
@app.route('/login', methods=['POST'])
def login():
    username = request.form['username']
    password = request.form['password']

    if not os.path.exists("cred.csv"):
        return render_template("login.html", message="No users found ❌")

    with open("cred.csv", "r") as f:
        users = f.readlines()

    for user in users:
        data = user.strip().split(",")
        if len(data) == 3:
            u, e, p = data
            if u == username and p == password:
                return redirect("/dashboard")

    return render_template("login.html", message="Invalid Credentials ❌")


# ================= DASHBOARD =================
@app.route('/dashboard')
def dashboard():
    return render_template("dashboard.html")


if __name__ == '__main__':
    app.run(debug=True)