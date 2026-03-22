from flask import Flask, request, redirect, render_template, jsonify, session
import os
from simulation.sumo import get_lane_data

app = Flask(
    __name__,
    template_folder="fronted"
)
# required for session
app.secret_key = "traffic_secret_key"


# ================= API FOR SUMO =================
@app.route('/api/traffic')
def traffic_data():
    data = get_lane_data()
    return jsonify(data)


# ================= HOME =================
@app.route('/')
def home():
    return render_template("index.html")


# ================= LOGIN PAGE =================
@app.route('/login')
def login_page():
    return render_template("login.html")


# ================= SIGNUP PAGE =================
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

    with open("cred.csv", "a") as f:
        f.write(f"{username},{email},{password}\n")

    # login user automatically
    session['user'] = username

    return redirect("/dashboard")


# ================= LOGIN =================
@app.route('/login', methods=['POST'])
def login():
    username = request.form['username']
    password = request.form['password']

    if not os.path.exists("cred.csv"):
        return render_template("login.html", message="No users registered ❌")

    with open("cred.csv", "r") as f:
        users = f.readlines()

    for user in users:
        data = user.strip().split(",")
        if len(data) == 3:
            u, e, p = data
            if u == username and p == password:
                session['user'] = username
                return redirect("/dashboard")

    return render_template("login.html", message="Invalid username or password ❌")


# ================= DASHBOARD (PROTECTED) =================
@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        return redirect("/login")
    return render_template("dashboard.html", user=session['user'])


# ================= LOGOUT =================
@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect("/login")


# ================= RUN APP =================
if __name__ == '__main__':
    app.run(debug=True, use_reloader=False)