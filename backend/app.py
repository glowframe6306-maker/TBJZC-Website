from flask import Flask, jsonify, render_template_string, request

app = Flask(__name__)

SCHOOL = {
    "name": "T.B.Jaya Zahira Vidyalaya",
    "founding_year": 1921,
    "motto": "THE LEARNED IS ONE WHO PRACTICES WHAT HE KNOWS",
    "medium": ["SINHALA", "TAMIL"],
    "students_approx": 700,
    "teachers_approx": 60,
    "principal": "MR. M.R.M.MANZIL",
    "website_creator": "M.I.MUHAMMADH (2025 O/L BATCH)",
    "address": "24, SIR JAMES PEIRIS MAWATHA, COLOMBO 02",
    "phone": "0112 300 338",
    "email": "tbjzc2013@gmail.com",
    "facebook": "https://web.facebook.com/T.BJZAHIRAOFFICIAL/?_rdc=1&_rdr#",
    "colors": ["MEROON", "YELLOW", "GREEN"],
    "houses": [
        {"name": "RAFAH", "color": "GREEN"},
        {"name": "CAIRO", "color": "YELLOW"},
        {"name": "JUMAIL", "color": "MEROON"}
    ],
    "sports_clubs": ["FOOTBALL", "CRICKET", "HOCKEY", "KARATE", "CHESS"],
    "achievements": ["All island first places in Islamic cultural competitions", "2024 O/L 9A student"]
}

CLUBS = {
    "Sinhala Literary Association": {
        "teacher_in_charge": "MRS. SRIYANI EKANAYAKE",
        "president": "M.A. ABDUL AZEEZ",
        "secretary": "M.I.MUHAMMADH",
        "vice_president": "MAHDI RIZWI",
    },
    "Tamil Literary Association": {
        "teacher_in_charge": "MRS. M. M. F. MINHA",
        "president": "M.I.A.ASLAM",
        "secretary": "M.AKAM",
    },
    "English Literary Association": {
        "teacher_in_charge": "MRS. FAZREEN MOHAMED",
        "president": "M.RM.ALFATH",
    },
    # Additional clubs truncated for brevity; full data can be added as needed
}


@app.route('/info')
def info():
    return jsonify(SCHOOL)


@app.route('/clubs')
def clubs():
    q = request.args.get('q', '').lower()
    if q:
        filtered = {k: v for k, v in CLUBS.items() if q in k.lower()}
        return jsonify(filtered)
    return jsonify(CLUBS)


FRONT_HTML = '''
<!doctype html>
<html>
<head><meta charset="utf-8"><title>T.B.Jaya Zahira Vidyalaya</title></head>
<body style="font-family: Arial, sans-serif; text-align:center;">
  <h1 style="font-size:48px; margin-top:40px;">T.B.Jaya Zahira Vidyalaya</h1>
  <p><strong>Motto:</strong> THE LEARNED IS ONE WHO PRACTICES WHAT HE KNOWS</p>
  <p><strong>Founded:</strong> 1921</p>
  <form action="/search" method="get">
    <input name="q" placeholder="Search clubs...">
    <button type="submit">Search</button>
  </form>
</body>
</html>
'''


@app.route('/')
def frontpage():
    return render_template_string(FRONT_HTML)


@app.route('/search')
def search():
    q = request.args.get('q', '').lower()
    results = {k: v for k, v in CLUBS.items() if q in k.lower()} if q else {}
    return jsonify(results)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
