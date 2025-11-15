package scorer;

import models.Course;
import models.StudentProfile;

/**
 * Course Scorer - Scores courses based on multiple factors
 * 
 * Main Functions: 1. scoreCourse() - Calculate comprehensive score (0-100) 2.
 * predictGPA() - Predict student's expected GPA 3. calculateDifficulty() -
 * Calculate course difficulty 4. meetsBasicRequirements() - Check if course
 * meets student's basic requirements
 */
public class CourseScorer {

    // ========== Scoring Weight Configuration ==========
    // These weights determine the importance of each factor, should sum to 1.0
    private static final double WEIGHT_PROF_RATING = 0.25; // Professor rating weight 25%
    private static final double WEIGHT_A_RATE = 0.30; // A-rate weight 30%
    private static final double WEIGHT_RELEVANCE = 0.25; // Relevance weight 25%
    private static final double WEIGHT_TIME_PREF = 0.20; // Time preference weight 20%

    // ========== Core Method 1: Comprehensive Course Scoring ==========

    /**
     * Calculate comprehensive score for a course (0-100) Higher score means the
     * course is more suitable for the student
     * 
     * Scoring Formula: Total = Professor Rating×25% + A-Rate×30% + Relevance×25% +
     * Time Preference×20%
     * 
     * @param course  The course to be scored
     * @param profile Student profile (contains student preferences)
     * @return Comprehensive score (0-100), higher is better
     */
    public static double scoreCourse(Course course, StudentProfile profile) {
        double totalScore = 0.0;

        // 1. Professor rating component (convert 0-5 to 0-100)
        double profScore = (course.getProfRating() / 5.0) * 100;
        totalScore += profScore * WEIGHT_PROF_RATING;

        // 2. A-rate component (convert 0-1 to 0-100)
        double aRateScore = course.getARate() * 100;
        totalScore += aRateScore * WEIGHT_A_RATE;

        // 3. Relevance component
        double relevanceScore = calculateRelevanceScore(course, profile);
        totalScore += relevanceScore * WEIGHT_RELEVANCE;

        // 4. Time preference component
        double timeScore = calculateTimePreferenceScore(course, profile);
        totalScore += timeScore * WEIGHT_TIME_PREF;

        return totalScore;
    }

    // ========== Core Method 2: GPA Prediction ==========

    /**
     * Predict what GPA the student can achieve in this course
     * 
     * Strategy: - Base: Use course's historical average GPA - If student
     * prioritizes GPA, be conservative (×0.9) - If course has high A-rate (>70%),
     * be optimistic (×1.05)
     * 
     * @param course  The course
     * @param profile Student profile
     * @return Predicted GPA (0.0-4.0)
     */
    public static double predictGPA(Course course, StudentProfile profile) {
        double baseGPA = course.getAverageGPA();

        // If student prioritizes GPA, be conservative (×0.9)
        if (profile.isPrioritizeGPA()) {
            return baseGPA * 0.9;
        }

        // If course has high A-rate, can be more optimistic
        if (course.getARate() > 0.7) {
            return Math.min(4.0, baseGPA * 1.05); // Cannot exceed 4.0
        }

        // Otherwise use historical average
        return baseGPA;
    }

    // ========== Core Method 3: Calculate Difficulty ==========

    /**
     * Calculate course difficulty (0-100, higher means harder)
     * 
     * Difficulty Formula: - 70% from A-rate: (1 - A-rate) × 100 - 30% from
     * professor rating: (5 - prof rating) / 5 × 100
     * 
     * Example: - 90% A-rate, 5.0 prof rating → difficulty = 7 + 0 = 7 (very easy) -
     * 40% A-rate, 3.0 prof rating → difficulty = 60 + 40 = 100 (very hard)
     * 
     * @param course The course
     * @return Difficulty value (0-100)
     */
    public static double calculateDifficulty(Course course) {
        // Difficulty component 1: inferred from A-rate
        // Lower A-rate → harder course
        double difficultyFromGrade = (1.0 - course.getARate()) * 100;

        // Difficulty component 2: inferred from professor rating
        // Lower professor rating → possibly poor teaching or hard course
        double difficultyFromProf = ((5.0 - course.getProfRating()) / 5.0) * 100;

        // Combined difficulty (70% from grades, 30% from professor)
        return difficultyFromGrade * 0.7 + difficultyFromProf * 0.3;
    }

    // ========== Core Method 4: Check Basic Requirements ==========

    /**
     * Check if course meets student's basic requirements Used to filter out
     * obviously unsuitable courses
     * 
     * Filter Rules: 1. If student doesn't want early classes → Exclude early classes
     * 
     * 2. If student has high GPA goal (≥3.7) && course is too hard (A-rate<20%) →
     * Exclude
     * 
     * @param course  The course
     * @param profile Student profile
     * @return true=meets requirements, false=doesn't meet (should exclude)
     */
    public static boolean meetsBasicRequirements(Course course, StudentProfile profile) {
        // Rule 1: Early morning filter
        if (profile.isNoEarlyClass() && course.isEarlyMorning()) {
            return false; // Student doesn't want early classes, this is early, exclude!
        }

        // Rule 2: Difficulty filter (for students with high GPA goals)
        if (profile.getGpaGoal() >= 3.7) {
            if (course.getARate() < 0.4) { // Courses with A-rate below 40% are too hard
                return false; // Exclude courses that are too difficult
            }
        }

        // All other cases meet requirements
        return true;
    }

    // ========== Helper Method 1: Calculate Relevance Score ==========

    /**
     * Calculate course relevance score (0-100)
     * 
     * Scoring Logic: - Course marked as "both" (relevant to both paths) → 80 points
     * - Course perfectly matches student's career goal → 100 points - Course
     * doesn't match student's career goal → 30 points - Course has no relevance
     * marking → 50 points (neutral)
     * 
     * @param course  The course
     * @param profile Student profile
     * @return Relevance score (0-100)
     */
    private static double calculateRelevanceScore(Course course, StudentProfile profile) {
        String courseRelevance = course.getRelevance(); // "grad_school", "industry", "both"
        String careerGoal = profile.getCareerGoal(); // "grad_school" or "industry"

        // Course has no relevance marking, give medium score
        if (courseRelevance == null || courseRelevance.isEmpty()) {
            return 50.0;
        }

        // Course is relevant to both paths
        if ("both".equalsIgnoreCase(courseRelevance)) {
            return 80.0;
        }

        // Course perfectly matches student's goal
        if (courseRelevance.equalsIgnoreCase(careerGoal)) {
            return 100.0; // Highest score!
        }

        // Doesn't match, give lower score
        return 30.0;
    }

    // ========== Helper Method 2: Calculate Time Preference Score ==========

    /**
     * Calculate time preference score (0-100)
     * 
     * Scoring Logic: - Student doesn't care about time → 100 points (full score) -
     * Student doesn't want early classes && course is early → 0 points - Student
     * doesn't want early classes && course is not early → 100 points
     * 
     * @param course  The course
     * @param profile Student profile
     * @return Time preference score (0-100)
     */
    private static double calculateTimePreferenceScore(Course course, StudentProfile profile) {
        // Student doesn't care about time
        if (!profile.isNoEarlyClass()) {
            return 100.0; // Full score
        }

        // Student doesn't want early classes
        if (course.isEarlyMorning()) {
            return 0.0; // Early class gets 0 points
        }

        return 100.0; // Non-early class gets full score
    }

    // ========== Utility Method: Compare Two Courses ==========

    /**
     * Compare scores of two courses Used for sorting course lists
     * 
     * @param course1 Course 1
     * @param course2 Course 2
     * @param profile Student profile
     * @return Positive=course1 is better, Negative=course2 is better, 0=equally
     *         good
     */
    public static int compareCourses(Course course1, Course course2, StudentProfile profile) {
        double score1 = scoreCourse(course1, profile);
        double score2 = scoreCourse(course2, profile);
        return Double.compare(score1, score2);
    }

    // ========== Debug Method: Print Course Score Details ==========

    /**
     * Print detailed scoring information for a course (for debugging)
     * 
     * @param course  The course
     * @param profile Student profile
     */
    public static void printCourseScore(Course course, StudentProfile profile) {
        System.out.println("\n===== Course Score Details =====");
        System.out.println("Course: " + course.getCourseId() + " - " + course.getName());

        double profScore = (course.getProfRating() / 5.0) * 100;
        double aRateScore = course.getARate() * 100;
        double relevanceScore = calculateRelevanceScore(course, profile);
        double timeScore = calculateTimePreferenceScore(course, profile);
        double totalScore = scoreCourse(course, profile);

        System.out.printf("Professor Rating: %.1f (score: %.1f)%n", course.getProfRating(),
                profScore);
        System.out.printf("A Rate: %.0f%% (score: %.1f)%n", course.getARate() * 100, aRateScore);
        System.out.printf("Relevance: %s (score: %.1f)%n", course.getRelevance(), relevanceScore);
        System.out.printf("Time Preference: %s (score: %.1f)%n",
                course.isEarlyMorning() ? "Early" : "Normal", timeScore);
        System.out.printf("TOTAL SCORE: %.1f / 100%n", totalScore);
        System.out.printf("Difficulty: %.1f%n", calculateDifficulty(course));
        System.out.printf("Predicted GPA: %.2f%n", predictGPA(course, profile));
    }
}