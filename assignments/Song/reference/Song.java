// Reference solution
// Programming Assignment #1: Song
//
// Prints a shortened version of the folk song "Bought Me a Cat."
// Each verse has its own method, and the growing list of animal
// sounds is printed by methods that call each other.

public class Song {
    public static void main(String[] args) {
        catVerse();
        System.out.println();
        henVerse();
        System.out.println();
        duckVerse();
        System.out.println();
        gooseVerse();
        System.out.println();
        sheepVerse();
        System.out.println();
        pigVerse();
    }

    // Prints the cat verse.
    public static void catVerse() {
        System.out.println("Bought me a cat and the cat pleased me,");
        System.out.println("I fed my cat under yonder tree.");
        catSound();
    }

    // Prints the hen verse.
    public static void henVerse() {
        System.out.println("Bought me a hen and the hen pleased me,");
        System.out.println("I fed my hen under yonder tree.");
        henSounds();
    }

    // Prints the duck verse.
    public static void duckVerse() {
        System.out.println("Bought me a duck and the duck pleased me,");
        System.out.println("I fed my duck under yonder tree.");
        duckSounds();
    }

    // Prints the goose verse.
    public static void gooseVerse() {
        System.out.println("Bought me a goose and the goose pleased me,");
        System.out.println("I fed my goose under yonder tree.");
        gooseSounds();
    }

    // Prints the sheep verse.
    public static void sheepVerse() {
        System.out.println("Bought me a sheep and the sheep pleased me,");
        System.out.println("I fed my sheep under yonder tree.");
        sheepSounds();
    }

    // Prints the pig verse.
    public static void pigVerse() {
        System.out.println("Bought me a pig and the pig pleased me,");
        System.out.println("I fed my pig under yonder tree.");
        System.out.println("Pig goes oink, oink,");
        sheepSounds();
    }

    // Prints the sounds from the sheep back to the cat.
    public static void sheepSounds() {
        System.out.println("Sheep goes baa, baa,");
        gooseSounds();
    }

    // Prints the sounds from the goose back to the cat.
    public static void gooseSounds() {
        System.out.println("Goose goes hissy, hissy,");
        duckSounds();
    }

    // Prints the sounds from the duck back to the cat.
    public static void duckSounds() {
        System.out.println("Duck goes quack, quack,");
        henSounds();
    }

    // Prints the sounds from the hen back to the cat.
    public static void henSounds() {
        System.out.println("Hen goes chimmy-chuck, chimmy-chuck,");
        catSound();
    }

    // Prints the cat's sound, which ends every verse.
    public static void catSound() {
        System.out.println("Cat goes fiddle-i-fee.");
    }
}
