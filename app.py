
from flask import Flask, render_template
import sqlite3

app = Flask(__name__)

@app.route("/")
def home():
    conn = sqlite3.connect("flight_log.db")
    cursor = conn.cursor()
    cursor.execute("SELECT timestamp, flight_code, airline, departure, arrival, status FROM flights ORDER BY timestamp DESC")
    rows = cursor.fetchall()
    conn.close()
    return render_template("history.html", rows=rows)

if __name__ == "__main__":
    app.run(debug=True)
