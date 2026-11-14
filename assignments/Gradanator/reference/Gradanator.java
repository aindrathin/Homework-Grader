// Reference solution
// Programming Assignment #4: Gradanator
//
// This gradanator program calculates grades. It asks user for homework and test
// grades, and prints out an expected grade based on user input.

import java.util.*;

public class Gradanator {
    public static final int EXAM_MAX = 100;           // highest score an exam can count for
    public static final int POINTS_PER_SECTION = 5;   // points earned per section attended
    public static final int SECTION_MAX = 30;         // most section points that count

    public static void main(String[] args) {
        Scanner console = new Scanner(System.in);
        intro();
        double midterm = exam(console, "Midterm");
        double finalExam = exam(console, "Final");
        double homework = homework(console);
        double percentage = midterm + finalExam + homework;
        report(percentage);
    }

    // Prints a short explanation of the program.
    public static void intro() {
        System.out.println("This program reads exam/homework scores");
        System.out.println("and reports your overall course grade.");
        System.out.println();
    }

    // Reads the weight, score, and shift for one exam, prints its points, and
    // returns its weighted score.
    // console - reads the user's input
    // name - the exam's name, such as "Midterm"
    public static double exam(Scanner console, String name) {
        System.out.println(name + ":");
        int weight = readWeight(console);
        System.out.print("Score earned? ");
        int score = console.nextInt();
        System.out.print("Were scores shifted (1=yes, 2=no)? ");
        int shifted = console.nextInt();
        if (shifted == 1) {
            System.out.print("Shift amount? ");
            score += console.nextInt();
        }
        score = Math.min(score, EXAM_MAX);
        return printScores(score, EXAM_MAX, weight);
    }

    // Reads the weight, assignment scores, and section attendance for homework,
    // prints its points, and returns its weighted score.
    // console - reads the user's input
    public static double homework(Scanner console) {
        System.out.println("Homework:");
        int weight = readWeight(console);
        System.out.print("Number of assignments? ");
        int count = console.nextInt();
        int earned = 0;
        int possible = 0;
        for (int i = 1; i <= count; i++) {
            System.out.print("Assignment " + i + " score and max? ");
            earned += console.nextInt();
            possible += console.nextInt();
        }
        System.out.print("How many sections did you attend? ");
        int sectionPoints = Math.min(console.nextInt() * POINTS_PER_SECTION, SECTION_MAX);
        System.out.println("Section points = " + sectionPoints + " / " + SECTION_MAX);
        earned += sectionPoints;
        possible += SECTION_MAX;
        earned = Math.min(earned, possible);
        return printScores(earned, possible, weight);
    }

    // Prompts for and returns a category's weight.
    // console - reads the user's input
    public static int readWeight(Scanner console) {
        System.out.print("Weight (0-100)? ");
        return console.nextInt();
    }

    // Prints a category's total and weighted points, then returns the weighted score.
    // earned - points earned in the category
    // possible - points possible in the category
    // weight - the category's weight out of 100
    public static double printScores(int earned, int possible, int weight) {
        double weighted = (double) earned / possible * weight;
        System.out.println("Total points = " + earned + " / " + possible);
        System.out.printf("Weighted score = %.1f / %d\n", weighted, weight);
        System.out.println();
        return weighted;
    }

    // Prints the overall percentage, the lowest grade it guarantees, and a message.
    // percentage - the sum of the three weighted scores
    public static void report(double percentage) {
        System.out.printf("Overall percentage = %.1f\n", percentage);
        double grade = minimumGrade(percentage);
        System.out.printf("Your grade will be at least: %.1f\n", grade);
        if (grade == 3.0) {
            System.out.println("Excellent work, keep it up!");
        } else if (grade == 2.0) {
            System.out.println("Good job, you're on the right track.");
        } else if (grade == 0.7) {
            System.out.println("You passed, but there is room to grow.");
        } else {
            System.out.println("Time to visit office hours.");
        }
    }

    // Returns the lowest grade on the 4.0 scale that a percentage guarantees.
    // percentage - the overall course percentage
    public static double minimumGrade(double percentage) {
        if (percentage >= 85) {
            return 3.0;
        } else if (percentage >= 75) {
            return 2.0;
        } else if (percentage >= 60) {
            return 0.7;
        } else {
            return 0.0;
        }
    }
}
