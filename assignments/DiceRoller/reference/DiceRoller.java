import java.util.Scanner;

public class DiceRoller {
    public static void main(String[] args) {
        Scanner in = new Scanner(System.in);
        System.out.print("How many rolls? ");
        int rolls = in.nextInt();
        int total = 0;
        for (int i = 1; i <= rolls; i++) {
            int roll = (int) (Math.random() * 6) + 1;
            total += roll;
            System.out.println("Roll " + i + ": " + roll);
        }
        System.out.println("Total: " + total);
    }
}
