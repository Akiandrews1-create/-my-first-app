while True:
    print("\n=== Simple Calculator ===")

    try:
        num1 = float(input("Enter first number: "))
        num2 = float(input("Enter second number: "))
    except ValueError:
        print("❌ Invalid number, try again!")
        continue

    print("Choose operation (+, -, *, /)")
    op = input("Operation: ")

    if op == "+":
        result = num1 + num2
    elif op == "-":
        result = num1 - num2
    elif op == "*":
        result = num1 * num2
    elif op == "/":
        if num2 == 0:
            print("❌ Cannot divide by zero!")
            continue
        result = num1 / num2
    else:
        print("❌ Invalid operation!")
        continue

    print(f"✅ Result: {result}")

    again = input("Do another calculation? (y/n): ")
    if again.lower() != "y":
        print("👋 Bye bro!")
        break