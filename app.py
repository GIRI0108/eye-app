import os
import base64
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash,session, send_file, jsonify
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from pymongo import MongoClient
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from PIL import Image
from dotenv import load_dotenv
from bson import ObjectId
from openai import OpenAI
import pandas as pd
import random
import json


# Load env
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
SECRET_KEY = os.getenv("SECRET_KEY", "change_this_in_prod")

# OpenAI client
client = OpenAI(api_key=OPENAI_API_KEY)

# Flask app
app = Flask(__name__)
app.secret_key = SECRET_KEY
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

ALLOWED_EXT = {'png', 'jpg', 'jpeg'}
UPLOAD_FOLDER = os.path.join("static", "uploads")
REPORT_FOLDER = "reports"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(REPORT_FOLDER, exist_ok=True)

# MongoDB
mongo = MongoClient(MONGO_URI)
db = mongo['eye_ai_db']
users_col = db['users']
images_col = db['images']
vision_col = db['vision_tests']
profiles_col = db['patient_profiles']


# -------------------- Helpers --------------------
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXT

def save_file_storage(fs):
    fname = secure_filename(fs.filename)
    ts = datetime.utcnow().strftime("%Y%m%d%H%M%S%f")
    out = f"{ts}_{fname}"
    path = os.path.join(UPLOAD_FOLDER, out)
    fs.save(path)
    return path, out

# -------------------- AI FUNCTIONS --------------------
def call_openai_image_analysis_localfile(image_path):
    import base64

    with open(image_path, "rb") as img_file:
        img_bytes = img_file.read()
        b64_img = base64.b64encode(img_bytes).decode("utf-8")

    prompt = """
    You are a professional eye specialist doctor.

    Analyze this eye image and provide FULL medical report in:

    1. English
    2. Tamil

    Must include:
    - Disease Name if avaliable
    or any abnormalities found.
    like eye is very red or dry etc.
    if none found, say "No issues found".
    - Symptoms
    - Causes (How it happens)
    - What to do ✅
    - What NOT to do ❌
    - Health tips
    - Risk level
    Provide the response in structured format with headings with small content.with bullet points where necessary.
if not patter
    """

    response = client.responses.create(
        model="gpt-4.1-mini",
        input=[
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt},
                    {
                        "type": "input_image",
                        "image_url": f"data:image/jpeg;base64,{b64_img}"
                    }
                ]
            }
        ]
    )

    return {"model_response": response.output_text}


def call_openai_chatbot(user_text):
    prompt = f"""
    You are a medical eye specialist assistant.

    Answer in BOTH English and Tamil.

    Include:
    - Explanation
    - Symptoms
    - Causes
    - What to do ✅
    - What NOT to do ❌
    - Health tips

    Question:
    {user_text}
    """

    resp = client.responses.create(
        model="gpt-4.1-mini",
        input=prompt
    )
    return resp.output_text

def call_openai_vision_ai(score, total, weak_areas):
    prompt = f"""
You are a senior ophthalmologist.

A user completed a vision activity test.

Score: {score} / {total}
Weak areas: {", ".join(weak_areas)}

Generate a PROFESSIONAL vision risk report.

Include:
1. Risk Level (Low / Moderate / High)
2. What happened
3. Why it happened
4. What may happen if ignored
5. How to improve
6. What to avoid
7. Eye care tips

Language:
- English
- Tamil

Rules:
- Not a medical diagnosis
- Friendly professional tone
"""

    resp = client.responses.create(
        model="gpt-4.1-mini",
        input=prompt
    )
    return resp.output_text

# ---- Quiz helpers ----
def load_questions_from_excel(excel_path="static/games/vision_questions_40.xlsx"):
    """
    Returns list of question dicts with columns:
    id (int), image (relative path under static/games/), option1..option4, answer
    """
    if not os.path.exists(excel_path):
        return []
    df = pd.read_excel(excel_path, engine="openpyxl")
    # ensure consistent columns
    df = df.fillna('')
    questions = df.to_dict(orient="records")
    # ensure image path is relative to /static/games/
    for q in questions:
        if q.get("image"):
            # if user stored "questions/q01.png" keep it; if only filename, prefix folder
            if not q["image"].startswith("static/") and not q["image"].startswith("questions/"):
                q["image"] = f"questions/{q['image']}"
        else:
            q["image"] = ""
    return questions


# -------------------- Routes --------------------
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/register", methods=["GET","POST"])
def register():
    if request.method == "POST":
        username = request.form['username'].strip()
        password = request.form['password']
        role = request.form.get('role', 'Patient')

        if users_col.find_one({"username": username}):
            flash("Username exists")
            return redirect(url_for('register'))

        users_col.insert_one({
            "username": username,
            "password": generate_password_hash(password),
            "role": role,
            "created_at": datetime.utcnow()
        })
        return redirect(url_for('login'))
    return render_template("register.html")

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        username = request.form['username']
        password = request.form['password']

        user = users_col.find_one({"username": username})
        if not user or not check_password_hash(user['password'], password):
            flash("Invalid credentials")
            return redirect(url_for("login"))

        session['username'] = username
        session['role'] = user["role"]

        if user["role"] == "Technician":
            return redirect("/tech")
        return redirect("/patient")
    return render_template("login.html")

@app.route("/edit_profile", methods=["GET","POST"])
def edit_profile():
    if 'username' not in session or session["role"] != "Patient":
        return redirect("/login")

    user = session["username"]

    if request.method == "POST":
        data = {
            "username": user,
            "full_name": request.form["full_name"],
            "age": request.form["age"],
            "gender": request.form["gender"],
            "phone": request.form["phone"],
            "email": request.form["email"],
            "height": request.form["height"],
            "weight": request.form["weight"],
            "bp_systolic": request.form["bp_systolic"],
            "bp_diastolic": request.form["bp_diastolic"],
            "address": request.form["address"],
            "medical_history": request.form["medical_history"],
            "eye_history": request.form["eye_history"],
            "family_eye_history": request.form["family_eye_history"],
            "updated_at": datetime.utcnow()
        }

        profiles_col.update_one(
            {"username": user},
            {"$set": data},
            upsert=True
        )

        flash("Profile saved successfully ✅")
        return redirect("/patient")

    profile = profiles_col.find_one({"username": user})
    return render_template("edit_profile.html", profile=profile)


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

# -------------------- Patient --------------------
@app.route("/patient")
def patient_dashboard():
    if 'username' not in session or session['role'] != "Patient":
        return redirect("/login")

    user = session["username"]

    docs = list(images_col.find({"username": user}).sort("created_at",-1))
    profile = profiles_col.find_one({"username": user})

    return render_template(
        "patient_dashboard.html",
        images=docs,
        username=user,
        profile=profile
    )

@app.route("/upload", methods=["GET","POST"])
def upload():
    if 'username' not in session:
        return redirect("/login")

    if request.method == "POST":
        file = request.files.get("eye_image")
        if not file or file.filename == "":
            flash("No file selected")
            return redirect(request.url)

        if not allowed_file(file.filename):
            flash("Invalid file")
            return redirect(request.url)

        path, fname = save_file_storage(file)
        ai = call_openai_image_analysis_localfile(path)

        doc = {
            "username": session["username"],
            "filename": fname,
            "filepath": path,
            "ai_result": ai,
            "tech_validated": False,
            "created_at": datetime.utcnow()
        }

        res = images_col.insert_one(doc)
        return redirect(url_for("view_report", image_id=str(res.inserted_id)))

    return render_template("upload_image.html")

@app.route("/delete_scan/<scan_id>", methods=["POST"])
def delete_scan(scan_id):
    if 'username' not in session:
        return redirect("/login")

    from bson import ObjectId

    scan = images_col.find_one({"_id": ObjectId(scan_id)})

    # Security check – user can delete only their own scans
    if scan and scan["username"] == session["username"]:
        images_col.delete_one({"_id": ObjectId(scan_id)})

    return redirect("/patient")


@app.route("/chatbot", methods=["GET","POST"])
def chatbot():
    if "username" not in session:
        return redirect("/login")

    answer = None
    if request.method == "POST":
        q = request.form.get("question")
        answer = call_openai_chatbot(q)

    return render_template("chatbot.html", answer=answer)

@app.route("/vision_test", methods=["GET","POST"])
def vision_test():
    if "username" not in session:
        return redirect("/login")

    if request.method == "POST":
        answers = dict(request.form)

        ai_result = call_openai_vision_ai(answers)

        record = {
            "username": session["username"],
            "ai_result": ai_result,
            "created_at": datetime.utcnow()
        }
        vision_col.insert_one(record)

        return render_template("vision_test_result.html", result=record)

    return render_template("vision_test.html")

# ---------- Vision Quiz Routes (random 7 from Excel) ----------
@app.route("/vision/ready")
def vision_ready():
    if 'username' not in session:
        return redirect("/login")
    return render_template("vision_ready.html")


@app.route("/vision/face-capture")
def vision_face_capture():
    if 'username' not in session:
        return redirect("/login")
    return render_template("vision_face_capture.html")

@app.route("/vision/precheck", methods=["GET", "POST"])
def vision_precheck():
    if "username" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":
        # precheck completed
        session["vision_precheck_ok"] = True
        return redirect("/vision/user-details")

    return render_template("vision_precheck.html")



@app.route("/vision/user-details", methods=["GET","POST"])
def vision_user_details():
    if not session.get("vision_precheck_ok"):
        return redirect("/vision/precheck")

    if request.method == "POST":
        session["vision_user_details"] = dict(request.form)
        return redirect("/vision_quiz/start")

    return render_template("vision_user_details.html")





@app.route("/vision_quiz/start")
def vision_quiz_start():
    if 'username' not in session:
        return redirect(url_for("login"))

    all_qs = load_questions_from_excel()
    if len(all_qs) < 7:
        flash("Not enough questions available. Seed Excel first.", "danger")
        return redirect(url_for("patient_dashboard"))

    chosen = random.sample(all_qs, 7)
    # save only minimal required fields to session
    session['vision_quiz'] = {
        "questions": chosen,   # list of dicts
        "answers": {},         # idx -> user's answer
        "current": 0,
        "started_at": datetime.utcnow().isoformat()
    }
    session.modified = True
    return redirect(url_for("vision_quiz"))

@app.route("/vision_quiz")
def vision_quiz():
    if 'username' not in session or 'vision_quiz' not in session:
        return redirect(url_for("patient_dashboard"))

    quiz = session['vision_quiz']
    current = quiz.get("current", 0)
    total = len(quiz["questions"])
    q = quiz["questions"][current]
    # build full static path for image URL in template: url_for('static', filename='games/' + q['image'])
    return render_template("vision_quiz.html", q=q, index=current+1, total=total)

# API to fetch specific question by index (used by frontend when navigating)
@app.route("/vision_quiz/api/question/<int:idx>")
def vision_quiz_api_question(idx):
    if 'vision_quiz' not in session:
        return jsonify({"error":"not_started"}), 400
    quiz = session['vision_quiz']
    if idx < 0 or idx >= len(quiz["questions"]):
        return jsonify({"error":"out_of_range"}), 400
    q = quiz["questions"][idx]
    # return minimal safe payload (do not expose answer)
    payload = {
        "index": idx,
        "prompt": q.get("prompt",""),
        "image": url_for("static", filename="games/" + q.get("image","")),
        "options": [q.get("option1",""), q.get("option2",""), q.get("option3",""), q.get("option4","")],
        "type": q.get("type","single")
    }
    return jsonify(payload)

# API to submit/save answer (ajax)
@app.route("/vision_quiz/api/answer", methods=["POST"])
def vision_quiz_api_answer():
    if 'vision_quiz' not in session:
        return jsonify({"error":"not_started"}), 400
    data = request.get_json() or request.form
    idx = int(data.get("index", session['vision_quiz'].get("current", 0)))
    ans = data.get("answer","").strip()
    # store
    session['vision_quiz']['answers'][str(idx)] = ans
    # optionally advance
    if data.get("advance") in [True, "true", "True", "1"]:
        session['vision_quiz']['current'] = min(idx+1, len(session['vision_quiz']['questions'])-1)
    session.modified = True
    return jsonify({"ok": True})

# Finish and score
import difflib

def _normalize_ans(a):
    if a is None:
        return ""
    s = str(a).strip()
    # remove repeated whitespace
    s = " ".join(s.split())
    # normalize common punctuation
    s = s.replace("–", "-").replace("—", "-")
    return s.lower()

def _numeric_equal(a, b):
    # return True if both are numeric and equal as ints
    try:
        ai = int(float(a))
        bi = int(float(b))
        return ai == bi
    except Exception:
        return False

@app.route("/vision_quiz/finish", methods=["POST"])
def vision_quiz_finish():
    if 'vision_quiz' not in session:
        return redirect(url_for("patient_dashboard"))

    quiz = session.pop('vision_quiz', None)
    if not quiz:
        return redirect(url_for("patient_dashboard"))

    questions = quiz["questions"]
    answers = quiz.get("answers", {})

    correct_count = 0
    breakdown = []

    for i, q in enumerate(questions):
        correct_raw = q.get("answer", "")
        user_raw = answers.get(str(i), "")  # answers stored as strings keyed by index

        correct = _normalize_ans(correct_raw)
        user = _normalize_ans(user_raw)

        # First try exact normalized match
        ok = False
        reason = ""

        if correct == user and correct != "":
            ok = True
            reason = "exact match"
        else:
            # numeric flexibility: 6 == 06 == "6.0"
            if _numeric_equal(correct, user):
                ok = True
                reason = "numeric match"
            else:
                # try fuzzy (close match) but only if both are reasonably short text (avoid matching long texts)
                # use a conservative cutoff so we don't accidentally mark wrong answers correct
                try:
                    if len(correct) <= 40 and len(user) <= 40 and correct and user:
                        seq = difflib.SequenceMatcher(None, correct, user)
                        ratio = seq.ratio()
                        if ratio >= 0.78:
                            ok = True
                            reason = f"fuzzy match (ratio={ratio:.2f})"
                        else:
                            reason = f"no match (ratio={ratio:.2f})"
                    else:
                        reason = "no match (length or empty)"
                except Exception as e:
                    reason = f"error in fuzzy matching: {e}"

        if ok:
            correct_count += 1

        # Build breakdown entry (include raw values so you can debug)
        breakdown.append({
            "index": i,
            "image": url_for("static", filename="games/" + q.get("image","")),
            "prompt": q.get("prompt",""),
            "correct_raw": correct_raw,
            "user_raw": user_raw,
            "correct_norm": correct,
            "user_norm": user,
            "ok": ok,
            "reason": reason
        })

    # Score as percentage
       # Score as percentage
    score_pct = int(round((correct_count / max(1, len(questions))) * 100))

    total_q = len(questions)

    # Risk label
    if correct_count <= total_q * 0.4:
        risk_label = "High"
    elif correct_count <= total_q * 0.7:
        risk_label = "Moderate"
    else:
        risk_label = "Low"

    # Weak area detection
    weak_areas = []
    for b in breakdown:
        if not b["ok"]:
            text = (b.get("prompt") or "").lower()
            if "contrast" in text:
                weak_areas.append("Contrast Sensitivity")
            if "moving" in text or "tracking" in text:
                weak_areas.append("Visual Tracking")
            if "color" in text:
                weak_areas.append("Color Sensitivity")

    if not weak_areas:
        weak_areas = ["General visual fatigue"]

    # AI professional analysis
    ai_report = call_openai_vision_ai(
        score=correct_count,
        total=total_q,
        weak_areas=list(set(weak_areas))
    )

    insights = []
    if risk_label == "Low":
        insights.append("Overall vision appears healthy.")
    elif risk_label == "Moderate":
        insights.append("Mild visual stress detected. Monitor eye habits.")
    else:
        insights.append("High visual strain detected. Professional consultation advised.")


    # Save result to DB (store breakdown for future audit)
    result_doc = {
        "username": session.get("username"),
        "score": score_pct,
        "risk": risk_label,
        "ai_report": ai_report,
        "breakdown": breakdown,
        "insights": insights,
        "created_at": datetime.utcnow()
    }

    vision_col.insert_one(result_doc)


    # Render result page (template unchanged)
    return render_template(
     "vision_test_result.html",
        score=score_pct,
        risk=risk_label,
        insights=insights,
        breakdown=breakdown,
        ai_report=ai_report
    )




@app.route("/vision_history")
def vision_history():
    if 'username' not in session:
        return redirect(url_for("login"))
    docs = list(vision_col.find({"username": session['username']}).sort("created_at", -1).limit(10))
    # convert ObjectId and datetime to JSON-serializable
    history = []
    for d in docs:
        history.append({
            "score": d.get("score"),
            "risk_pct": d.get("risk_pct"),
            "created_at": d.get("created_at").isoformat() if d.get("created_at") else ""
        })
    return render_template("vision_history.html", history=history)


# -------------------- Reports --------------------
@app.route("/report/<image_id>")
def view_report(image_id):
    doc = images_col.find_one({"_id": ObjectId(image_id)})
    if not doc:
        return redirect("/patient")
    return render_template("report_view.html", doc=doc)

@app.route("/report/pdf/<image_id>")
def report_pdf(image_id):
    doc = images_col.find_one({"_id": ObjectId(image_id)})
    if not doc:
        return redirect("/")

    pdf_path = os.path.join(REPORT_FOLDER, f"report_{image_id}.pdf")
    c = canvas.Canvas(pdf_path, pagesize=letter)

    y = 750
    text = doc["ai_result"]["model_response"]

    for line in text.split("\n"):
        c.drawString(50, y, line[:100])
        y -= 14
        if y < 100:
            c.showPage()
            y = 750

    c.save()
    return send_file(pdf_path, as_attachment=True)

# -------------------- Technician --------------------
@app.route("/tech")
def tech_dashboard():
    if 'username' not in session or session["role"] != "Technician":
        return redirect("/login")

    docs = list(images_col.find().sort("created_at",-1))
    return render_template("tech_dashboard.html", images=docs)

@app.route("/tech/validate/<image_id>", methods=["GET","POST"])
def tech_validate(image_id):
    if 'username' not in session or session["role"] != "Technician":
        return redirect("/login")

    doc = images_col.find_one({"_id": ObjectId(image_id)})

    if request.method == "POST":
        notes = request.form.get("notes")
        images_col.update_one(
            {"_id": ObjectId(image_id)},
            {"$set":{
                "tech_validated":True,
                "tech_notes":notes
            }}
        )
        return redirect("/tech")

    return render_template("tech_validate.html", doc=doc)

# -------------------- API --------------------
@app.route("/api/upload", methods=["POST"])
def api_upload():
    username = request.form.get("username")
    file = request.files.get("image")

    if not file:
        return jsonify({"error":"no file"})

    path, fname = save_file_storage(file)
    ai = call_openai_image_analysis_localfile(path)

    doc = {
        "username": username,
        "filename": fname,
        "filepath": path,
        "ai_result": ai,
        "created_at": datetime.utcnow()
    }

    res = images_col.insert_one(doc)
    return jsonify({"success":True,"id":str(res.inserted_id)})

# -------------------- Run --------------------
if __name__ == "__main__":
    app.run(debug=True)
