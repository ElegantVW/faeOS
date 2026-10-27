package main

import (
	"fmt"
	"math"
	"os"
	"strconv"
	"strings"
)

func main() {
	fmt.Println("Abacus Calculator (type 'exit' to quit)")
	for {
		var input string
		fmt.Print("> ")
		fmt.Scanln(&input)
		if input == "exit" {
			break
		}
		fields := strings.Fields(input)
		if len(fields) != 3 {
			fmt.Println("Invalid format. Use 'a + b'")
			continue
		}
		a, _ := strconv.ParseFloat(fields[0], 64)
		b, _ := strconv.ParseFloat(fields[2], 64)
		op := fields[1]
		var result float64
		switch op {
		case "+":
			result = a + b
		case "-":
			result = a - b
		case "*":
			result = a * b
		case "/":
			if b == 0 {
				fmt.Println("Division by zero!")
				continue
			}
			result = a / b
		default:
			fmt.Println("Unknown operator. Use +, -, *, or /")
			continue
		}
		fmt.Printf("Result: %v\n", result)
	}
}