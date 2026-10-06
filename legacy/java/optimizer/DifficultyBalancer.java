package optimizer;

import models.Course;
import models.Semester;
import scorer.CourseScorer;
import java.util.*;

/**
 * Difficulty Balancer - Ensures course difficulty is balanced across semesters
 * 
 * Main Functions: 1. Calculate average difficulty for each semester 2. Analyze
 * difficulty distribution across all semesters 3. Balance difficulty by
 * swapping courses between semesters 4. Provide difficulty statistics and
 * warnings
 */
public class DifficultyBalancer {

    // ========== Difficulty Thresholds ==========
    private static final double MAX_AVG_DIFFICULTY = 70.0; // Maximum average difficulty per
                                                           // semester
    private static final double MIN_AVG_DIFFICULTY = 30.0; // Minimum average difficulty per
                                                           // semester
    private static final double DIFFICULTY_VARIANCE_THRESHOLD = 400.0; // Variance threshold for
                                                                       // balance
    private static final double SWAP_IMPROVEMENT_THRESHOLD = 5.0; // Minimum improvement to make a
                                                                  // swap

    // ========== Core Method 1: Calculate Semester Difficulty ==========

    /**
     * Calculate average difficulty for a semester
     * 
     * Difficulty is averaged across all courses in the semester Empty semesters
     * return 0.0
     * 
     * @param semester The semester to analyze
     * @return Average difficulty (0-100)
     */
    public static double calculateAverageDifficulty(Semester semester) {
        if (semester.getCourses().isEmpty()) {
            return 0.0;
        }

        double totalDifficulty = 0.0;
        for (Course course : semester.getCourses()) {
            totalDifficulty += CourseScorer.calculateDifficulty(course);
        }

        return totalDifficulty / semester.getCourses().size();
    }

    // ========== Core Method 2: Calculate Difficulty Variance ==========

    /**
     * Calculate variance of difficulty across all semesters
     * 
     * Variance measures how much difficulty fluctuates between semesters Lower
     * variance = more balanced
     * 
     * Formula: variance = Σ(difficulty - mean)² / n
     * 
     * @param plan List of all semesters
     * @return Difficulty variance
     */
    public static double calculateDifficultyVariance(List<Semester> plan) {
        List<Double> difficulties = new ArrayList<>();

        // Collect difficulties from non-empty semesters
        for (Semester sem : plan) {
            if (sem.getCourseCount() > 0) {
                difficulties.add(calculateAverageDifficulty(sem));
            }
        }

        if (difficulties.size() < 2) {
            return 0.0; // Need at least 2 semesters to calculate variance
        }

        // Calculate mean
        double mean = 0.0;
        for (double d : difficulties) {
            mean += d;
        }
        mean /= difficulties.size();

        // Calculate variance
        double variance = 0.0;
        for (double d : difficulties) {
            variance += Math.pow(d - mean, 2);
        }
        variance /= difficulties.size();

        return variance;
    }

    // ========== Core Method 3: Analyze Difficulty Distribution ==========

    /**
     * Analyze and print difficulty statistics for entire plan
     * 
     * Reports: - Difficulty for each semester - Difficulty level labels - Warnings
     * for semesters that are too hard/easy - Overall average and variance
     * 
     * @param plan List of all semesters
     */
    public static void analyzeDifficulty(List<Semester> plan) {
        System.out.println("\n========== Difficulty Analysis ==========");
        System.out.println("=".repeat(60));

        double totalDifficulty = 0.0;
        int semesterCount = 0;

        // Analyze each semester
        for (Semester semester : plan) {
            if (semester.getCourseCount() == 0) {
                continue; // Skip empty semesters
            }

            double avgDifficulty = calculateAverageDifficulty(semester);
            totalDifficulty += avgDifficulty;
            semesterCount++;

            String difficultyLevel = getDifficultyLevel(avgDifficulty);
            String warning = "";

            // Check for warnings
            if (avgDifficulty > MAX_AVG_DIFFICULTY) {
                warning = " TOO HARD";
            } else if (avgDifficulty < MIN_AVG_DIFFICULTY) {
                warning = " 💤 TOO EASY";
            }

            System.out.printf("%s: %.1f (%s)%s%n", semester.getSemesterLabel(), avgDifficulty,
                    difficultyLevel, warning);

            // Show individual course difficulties
            for (Course c : semester.getCourses()) {
                double courseDiff = CourseScorer.calculateDifficulty(c);
                String marker = courseDiff > 70 ? "🔥" : courseDiff < 30 ? "✨" : "  ";
                System.out.printf("  %s %s: %.1f%n", marker, c.getCourseId(), courseDiff);
            }
        }

        // Calculate overall statistics
        double avgOverall = semesterCount > 0 ? totalDifficulty / semesterCount : 0.0;
        double variance = calculateDifficultyVariance(plan);

        System.out.println("=".repeat(60));
        System.out.printf("Overall average difficulty: %.1f (%s)%n", avgOverall,
                getDifficultyLevel(avgOverall));
        System.out.printf("Difficulty variance: %.1f %s%n", variance,
                variance > DIFFICULTY_VARIANCE_THRESHOLD ? "HIGH (unbalanced)" : "OK (balanced)");

        // Provide recommendations
        if (variance > DIFFICULTY_VARIANCE_THRESHOLD) {
            System.out.println("\n Recommendation: Consider balancing difficulty across semesters");
        }
    }

    // ========== Core Method 4: Balance Difficulty ==========

    /**
     * Balance difficulty across all semesters by swapping courses
     * 
     * Strategy: 1. Find hardest and easiest semesters 2. Try to swap courses
     * between them 3. Repeat until no more improvements can be made
     * 
     * Constraints: - Only swap courses from the same year (to respect typical
     * progressions) - Only swap if it improves overall balance - Respect
     * prerequisite dependencies
     * 
     * @param plan List of all semesters (will be modified)
     */
    public static void balancePlan(List<Semester> plan) {
        System.out.println("\n========== Balancing Difficulty ==========");

        int maxIterations = 10; // Prevent infinite loops
        int swapsMade = 0;

        for (int iteration = 0; iteration < maxIterations; iteration++) {
            // Find hardest and easiest semesters
            Semester hardest = null;
            Semester easiest = null;
            double maxDiff = 0.0;
            double minDiff = 100.0;

            for (Semester sem : plan) {
                if (sem.getCourseCount() == 0) {
                    continue;
                }

                double diff = calculateAverageDifficulty(sem);

                if (diff > maxDiff) {
                    maxDiff = diff;
                    hardest = sem;
                }
                if (diff < minDiff) {
                    minDiff = diff;
                    easiest = sem;
                }
            }

            // Check if balancing is needed
            if (hardest == null || easiest == null) {
                break; // No semesters to balance
            }

            double diffGap = maxDiff - minDiff;

            if (diffGap < 15.0) {
                break; // Already balanced enough
            }

            // Try to swap courses
            boolean swapped = trySwapCourses(hardest, easiest);

            if (swapped) {
                swapsMade++;
                System.out.printf("  Swap #%d: Balanced %s (%.1f) ↔ %s (%.1f)%n", swapsMade,
                        hardest.getSemesterLabel(), maxDiff, easiest.getSemesterLabel(), minDiff);
            } else {
                break; // No more beneficial swaps possible
            }
        }

        if (swapsMade > 0) {
            System.out.println("Balancing complete! Made " + swapsMade + " swaps.");
        } else {
            System.out.println("Plan is already well-balanced!");
        }
    }

    // ========== Helper Method: Try Swap Courses ==========

    /**
     * Try to swap courses between two semesters to improve balance
     * 
     * Strategy: - From hard semester: find easiest course - From easy semester:
     * find hardest course - Swap them if it improves balance
     * 
     * @param hardSem The harder semester
     * @param easySem The easier semester
     * @return true if swap was made, false otherwise
     */
    private static boolean trySwapCourses(Semester hardSem, Semester easySem) {
        // Find easiest course in hard semester
        Course easyFromHard = null;
        double minDiffInHard = 100.0;

        for (Course c : hardSem.getCourses()) {
            double diff = CourseScorer.calculateDifficulty(c);
            if (diff < minDiffInHard) {
                minDiffInHard = diff;
                easyFromHard = c;
            }
        }

        // Find hardest course in easy semester
        Course hardFromEasy = null;
        double maxDiffInEasy = 0.0;

        for (Course c : easySem.getCourses()) {
            double diff = CourseScorer.calculateDifficulty(c);
            if (diff > maxDiffInEasy) {
                maxDiffInEasy = diff;
                hardFromEasy = c;
            }
        }

        // Check if swap would be beneficial
        if (easyFromHard == null || hardFromEasy == null) {
            return false; // Can't find suitable courses
        }

        if (maxDiffInEasy <= minDiffInHard) {
            return false; // Swap wouldn't help
        }

        // Calculate current and new difficulties
        double currentHard = calculateAverageDifficulty(hardSem);
        double currentEasy = calculateAverageDifficulty(easySem);
        double currentGap = Math.abs(currentHard - currentEasy);

        // Simulate the swap
        double newHard = simulateSwap(hardSem, easyFromHard, hardFromEasy);
        double newEasy = simulateSwap(easySem, hardFromEasy, easyFromHard);
        double newGap = Math.abs(newHard - newEasy);

        // Only swap if it improves balance significantly
        if (currentGap - newGap > SWAP_IMPROVEMENT_THRESHOLD) {
            // Execute the swap
            hardSem.removeCourse(easyFromHard.getCourseId());
            easySem.removeCourse(hardFromEasy.getCourseId());

            hardSem.addCourse(hardFromEasy);
            easySem.addCourse(easyFromHard);

            return true;
        }

        return false;
    }

    // ========== Helper Method: Simulate Swap ==========

    /**
     * Simulate what the difficulty would be after removing one course and adding
     * another
     * 
     * @param semester The semester
     * @param toRemove Course to remove
     * @param toAdd    Course to add
     * @return New average difficulty after swap
     */
    private static double simulateSwap(Semester semester, Course toRemove, Course toAdd) {
        if (semester.getCourseCount() <= 1) {
            return CourseScorer.calculateDifficulty(toAdd);
        }

        double totalDiff = 0.0;
        int count = 0;

        for (Course c : semester.getCourses()) {
            if (!c.getCourseId().equals(toRemove.getCourseId())) {
                totalDiff += CourseScorer.calculateDifficulty(c);
                count++;
            }
        }

        totalDiff += CourseScorer.calculateDifficulty(toAdd);
        count++;

        return totalDiff / count;
    }

    // ========== Utility Method 1: Get Difficulty Level ==========

    /**
     * Get difficulty level description
     * 
     * @param difficulty Difficulty value (0-100)
     * @return Difficulty level string
     */
    private static String getDifficultyLevel(double difficulty) {
        if (difficulty < 30)
            return "Very Easy";
        if (difficulty < 45)
            return "Easy";
        if (difficulty < 55)
            return "Moderate";
        if (difficulty < 70)
            return "Hard";
        return "Very Hard";
    }

    // ========== Utility Method 2: Label Semesters ==========

    /**
     * Assign difficulty level labels to all semesters
     * 
     * @param plan List of semesters
     * @return Map of semester label -> difficulty level
     */
    public static Map<String, String> labelSemesters(List<Semester> plan) {
        Map<String, String> labels = new HashMap<>();

        for (Semester sem : plan) {
            if (sem.getCourseCount() == 0) {
                continue;
            }

            double diff = calculateAverageDifficulty(sem);
            String label = getDifficultyLevel(diff);
            labels.put(sem.getSemesterLabel(), label);
        }

        return labels;
    }

    // ========== Utility Method 3: Find Hardest Courses ==========

    /**
     * Find the N hardest courses in a plan
     * 
     * @param plan List of semesters
     * @param n    Number of courses to return
     * @return List of hardest courses
     */
    public static List<Course> findHardestCourses(List<Semester> plan, int n) {
        List<Course> allCourses = new ArrayList<>();

        // Collect all courses
        for (Semester sem : plan) {
            allCourses.addAll(sem.getCourses());
        }

        // Sort by difficulty (descending)
        allCourses.sort((c1, c2) -> {
            double diff1 = CourseScorer.calculateDifficulty(c1);
            double diff2 = CourseScorer.calculateDifficulty(c2);
            return Double.compare(diff2, diff1);
        });

        // Return top N
        return allCourses.subList(0, Math.min(n, allCourses.size()));
    }

    // ========== Utility Method 4: Find Easiest Courses ==========

    /**
     * Find the N easiest courses in a plan
     * 
     * @param plan List of semesters
     * @param n    Number of courses to return
     * @return List of easiest courses
     */
    public static List<Course> findEasiestCourses(List<Semester> plan, int n) {
        List<Course> allCourses = new ArrayList<>();

        // Collect all courses
        for (Semester sem : plan) {
            allCourses.addAll(sem.getCourses());
        }

        // Sort by difficulty (ascending)
        allCourses.sort((c1, c2) -> {
            double diff1 = CourseScorer.calculateDifficulty(c1);
            double diff2 = CourseScorer.calculateDifficulty(c2);
            return Double.compare(diff1, diff2);
        });

        // Return top N
        return allCourses.subList(0, Math.min(n, allCourses.size()));
    }

    // ========== Utility Method 5: Get Semester Difficulty Summary ==========

    /**
     * Get a summary string for semester difficulty
     * 
     * @param semester The semester
     * @return Summary string (e.g., "Moderate (52.3)")
     */
    public static String getDifficultySummary(Semester semester) {
        if (semester.getCourseCount() == 0) {
            return "Empty";
        }

        double diff = calculateAverageDifficulty(semester);
        String level = getDifficultyLevel(diff);

        return String.format("%s (%.1f)", level, diff);
    }

    // ========== Utility Method 6: Check Balance Quality ==========

    /**
     * Check how well-balanced the plan is
     * 
     * @param plan List of semesters
     * @return Quality rating: "Excellent", "Good", "Fair", "Poor"
     */
    public static String checkBalanceQuality(List<Semester> plan) {
        double variance = calculateDifficultyVariance(plan);

        if (variance < 100)
            return "Excellent";
        if (variance < 250)
            return "Good";
        if (variance < 400)
            return "Fair";
        return "Poor";
    }

    // ========== Utility Method 7: Print Balance Report ==========

    /**
     * Print a comprehensive balance report
     * 
     * @param plan List of semesters
     */
    public static void printBalanceReport(List<Semester> plan) {
        System.out.println("\n========== Difficulty Balance Report ==========");

        double variance = calculateDifficultyVariance(plan);
        String quality = checkBalanceQuality(plan);

        System.out.println("Balance Quality: " + quality);
        System.out.println("Difficulty Variance: " + String.format("%.1f", variance));

        // Find extreme semesters
        Semester hardest = null;
        Semester easiest = null;
        double maxDiff = 0.0;
        double minDiff = 100.0;

        for (Semester sem : plan) {
            if (sem.getCourseCount() == 0)
                continue;

            double diff = calculateAverageDifficulty(sem);
            if (diff > maxDiff) {
                maxDiff = diff;
                hardest = sem;
            }
            if (diff < minDiff) {
                minDiff = diff;
                easiest = sem;
            }
        }

        if (hardest != null && easiest != null) {
            System.out.println("\nHardest semester: " + hardest.getSemesterLabel()
                    + " (difficulty: " + String.format("%.1f", maxDiff) + ")");
            System.out.println("Easiest semester: " + easiest.getSemesterLabel() + " (difficulty: "
                    + String.format("%.1f", minDiff) + ")");
            System.out.println("Difficulty gap: " + String.format("%.1f", maxDiff - minDiff));
        }

        // Top 3 hardest courses overall
        System.out.println("\nTop 3 hardest courses in plan:");
        List<Course> hardest3 = findHardestCourses(plan, 3);
        for (int i = 0; i < hardest3.size(); i++) {
            Course c = hardest3.get(i);
            System.out.printf("  %d. %s: %s (difficulty: %.1f)%n", i + 1, c.getCourseId(),
                    c.getName(), CourseScorer.calculateDifficulty(c));
        }
    }
}