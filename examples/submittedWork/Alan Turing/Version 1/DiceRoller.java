package dice;

import java.util.Random;
import java.util.Scanner;

public class DiceRoller {
    public static void main(String[] args) {
        Random rng = new Random();
        Scanner in = new Scanner(System.in);
        System.out.print("How many rolls? ");
        int rolls = in.nextInt();
        int total = 0;
        for (int i = 1; i <= rolls; i++) {
            int roll = (int) (rng.nextDouble() * 6) + 1;
            total += roll;
            System.out.println("Roll " + i + ": " + roll);
        }
        System.out.println("Total: " + total);
    }
}
