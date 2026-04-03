from flask import Flask, request, render_template
import os

app = Flask(__name__)

history = []

@app.route("/", methods=["GET", "POST"])
def calculator():
    result = ""

    if request.method == "POST":
        try:
            num1 = float(request.form["num1"])
            num2 = float(request.form["num2"])
            op = request.form["operation"]

            if op == "+":
                result = num1 + num2
            elif op == "-":
                result = num1 - num2
            elif op == "*":
                result = num1 * num2
            elif op == "/":
                if num2 == 0:
                    result = "Cannot divide by zero"
                else:
                    result = num1 / num2
            else:
                result = "Invalid operation"

            history.append(f"{num1} {op} {num2} = {result}")

        except ValueError:
            result = "Please enter valid numbers"

    return render_template("index.html", result=result, history=history)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))