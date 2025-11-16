package optimizer;

import models.Course;
import java.util.*;

/**
 * Double Major Helper - Assists with double major course planning
 * 
 * Main Functions: 1. Find overlap courses between two majors 2. Merge
 * requirements from two majors 3. Calculate total credits needed 4. Check if
 * double major is feasible in 4 years
 */
public class DoubleMajorHelper {

    // ========== Core Method 1: Find Overlap Courses ==========

    /**
     * Find courses that count for both majors (overlap courses) These are valuable
     * for double major students as they satisfy requirements for both majors
     * 
     * Example: MATH 340 (Linear Algebra) might count for both CS and MATH majors
     * 
     * @param allCourses List of all available courses
     * @param major1     First major name (e.g., "CS")
     * @param major2     Second major name (e.g., "MATH")
     * @return List of courses that belong to both majors
     */
    public static List<Course> findOverlapCourses(List<Course> allCourses, String major1,
            String major2) {
        List<Course> overlapCourses = new ArrayList<>();

        for (Course course : allCourses) {
            // Check if course belongs to both majors
            if (course.belongsToMajor(major1) && course.belongsToMajor(major2)) {
                overlapCourses.add(course);
            }
        }

        return overlapCourses;
    }

    // ========== Core Method 2: Get Required Courses for a Major ==========

    /**
     * Get list of required courses for a specific major
     * 
     * NOTE: In a real application, this should be loaded from a database For now,
     * we hardcode common major requirements
     * 
     * @param major Major name (e.g., "CS", "MATH", "ECE")
     * @return List of required course IDs
     */
    public static List<String> getRequiredCourses(String major) {
        // Map of major -> required courses
        Map<String, List<String>> majorRequirements = new HashMap<>();

        // Computer Science major requirements
        majorRequirements.put("CS", Arrays.asList("CS 200", "CS 300", "CS 400", "CS 500", "CS 354",
                "CS 577", "CS 540", "MATH 221", "MATH 222", "MATH 340" // Math courses that CS
                                                                       // requires
        ));

        // Mathematics major requirements
        majorRequirements.put("MATH", Arrays.asList("MATH 221", "MATH 222", "MATH 234", "MATH 340",
                "MATH 341", "MATH 421", "MATH 467", "CS 200", "CS 300" // CS courses that MATH
                                                                       // requires
        ));

        // Electrical & Computer Engineering requirements
        majorRequirements.put("ECE", Arrays.asList("ECE 203", "ECE 252", "ECE 330", "ECE 352",
                "ECE 354", "ECE 420", "MATH 221", "MATH 222", "MATH 234", "CS 200", "CS 300"));

        // Statistics major requirements
        majorRequirements.put("STAT", Arrays.asList("STAT 324", "STAT 371", "STAT 424", "STAT 451",
                "MATH 221", "MATH 222", "MATH 340", "CS 200", "CS 300"));

        // Data Science major requirements
        majorRequirements.put("DS", Arrays.asList("CS 200", "CS 300", "CS 400", "CS 540",
                "STAT 324", "STAT 371", "MATH 221", "MATH 222", "MATH 340"));

        // Return the required courses for the given major
        // If major not found, return empty list
        return majorRequirements.getOrDefault(major, new ArrayList<>());
    }

    // ========== Core Method 3: Merge Requirements ==========

    /**
     * Merge requirements from two majors, removing duplicates Also identifies and
     * reports overlap courses
     * 
     * Example: - CS requires: [CS 200, CS 300, MATH 221, MATH 222] - MATH requires:
     * [MATH 221, MATH 222, MATH 340, MATH 341] - Merged: [CS 200, CS 300, MATH 221,
     * MATH 222, MATH 340, MATH 341] - Overlap: [MATH 221, MATH 222] (counts for
     * both majors!)
     * 
     * @param major1     First major name
     * @param major2     Second major name
     * @param allCourses List of all courses (to find overlap courses)
     * @return List of unique course IDs needed for both majors
     */
    public static List<String> mergeRequirements(String major1, String major2,
            List<Course> allCourses) {
        Set<String> required = new HashSet<>();

        // Get requirements for each major
        List<String> major1Reqs = getRequiredCourses(major1);
        List<String> major2Reqs = getRequiredCourses(major2);

        // Add all requirements (Set automatically removes duplicates)
        required.addAll(major1Reqs);
        required.addAll(major2Reqs);

        // Find overlap courses
        List<Course> overlaps = findOverlapCourses(allCourses, major1, major2);

        // Print analysis
        System.out.println("\n========== Double Major Analysis ==========");
        System.out.println("Major 1 (" + major1 + "): " + major1Reqs.size() + " required courses");
        System.out.println("Major 2 (" + major2 + "): " + major2Reqs.size() + " required courses");
        System.out.println("Overlap courses: " + overlaps.size());

        if (!overlaps.isEmpty()) {
            System.out.println("\nCourses that count for BOTH majors:");
            for (Course c : overlaps) {
                System.out.println("  • " + c.getCourseId() + ": " + c.getName());
            }
        }

        System.out.println("\nTotal unique courses needed: " + required.size());
        System.out.println("Credits saved by overlap: "
                + (major1Reqs.size() + major2Reqs.size() - required.size()) + " courses");

        return new ArrayList<>(required);
    }

    // ========== Core Method 4: Calculate Total Credits ==========

    /**
     * Calculate total credits needed to complete all required courses
     * 
     * @param requiredCourses List of required course IDs
     * @param allCourses      List of all available courses
     * @return Total number of credits
     */
    public static int calculateTotalCredits(List<String> requiredCourses, List<Course> allCourses) {
        int total = 0;

        for (String courseId : requiredCourses) {
            // Find the course in allCourses
            for (Course c : allCourses) {
                if (c.getCourseId().equals(courseId)) {
                    total += c.getCredits();
                    break;
                }
            }
        }

        return total;
    }

    // ========== Core Method 5: Feasibility Check ==========

    /**
     * Check if completing a double major is feasible in 4 years
     * 
     * Calculation: - 4 years = 8 semesters - Total available credits =
     * maxCreditsPerSem × 8 - If total required credits ≤ available credits, it's
     * feasible
     * 
     * @param requiredCourses  List of required course IDs
     * @param allCourses       List of all available courses
     * @param maxCreditsPerSem Maximum credits student can take per semester
     * @return true if feasible, false otherwise
     */
    public static boolean isFeasible(List<String> requiredCourses, List<Course> allCourses,
            int maxCreditsPerSem) {
        int totalCreditsNeeded = calculateTotalCredits(requiredCourses, allCourses);
        int maxCreditsIn4Years = maxCreditsPerSem * 8; // 8 semesters in 4 years

        System.out.println("\n========== Feasibility Check ==========");
        System.out.println("Total credits needed: " + totalCreditsNeeded);
        System.out.println("Maximum credits available (4 years): " + maxCreditsIn4Years);
        System.out.println("Credits per semester: " + maxCreditsPerSem);

        boolean feasible = totalCreditsNeeded <= maxCreditsIn4Years;

        if (feasible) {
            int creditsLeft = maxCreditsIn4Years - totalCreditsNeeded;
            System.out.println(
                    "FEASIBLE! You'll have " + creditsLeft + " credits left for electives.");
        } else {
            int creditsShort = totalCreditsNeeded - maxCreditsIn4Years;
            System.out.println("NOT FEASIBLE! You're short by " + creditsShort + " credits.");
            System.out.println("Suggestions:");
            System.out.println("  1. Increase credits per semester to "
                    + (int) Math.ceil((double) totalCreditsNeeded / 8));
            System.out.println("  2. Take summer courses");
            System.out.println("  3. Consider dropping the second major");
        }

        return feasible;
    }

    // ========== Utility Method 1: Get Overlap Count ==========

    /**
     * Count how many courses overlap between two majors
     * 
     * @param major1 First major
     * @param major2 Second major
     * @return Number of overlapping courses
     */
    public static int getOverlapCount(String major1, String major2) {
        List<String> major1Reqs = getRequiredCourses(major1);
        List<String> major2Reqs = getRequiredCourses(major2);

        Set<String> set1 = new HashSet<>(major1Reqs);
        Set<String> set2 = new HashSet<>(major2Reqs);

        // Find intersection
        set1.retainAll(set2);

        return set1.size();
    }

    // ========== Utility Method 2: Suggest Best Double Major Pairs ==========

    /**
     * Suggest which majors pair well together (have high overlap)
     * 
     * @param primaryMajor Student's primary major
     * @return Map of secondary major -> overlap count, sorted by overlap
     */
    public static Map<String, Integer> suggestDoubleMajorPairs(String primaryMajor) {
        String[] allMajors = { "CS", "MATH", "ECE", "STAT", "DS" };
        Map<String, Integer> suggestions = new HashMap<>();

        for (String secondMajor : allMajors) {
            if (!secondMajor.equals(primaryMajor)) {
                int overlap = getOverlapCount(primaryMajor, secondMajor);
                suggestions.put(secondMajor, overlap);
            }
        }

        System.out.println(
                "\n========== Double Major Suggestions for " + primaryMajor + " ==========");
        System.out.println("Best pairings (by number of overlapping courses):");

        // Sort by overlap count (descending)
        suggestions.entrySet().stream().sorted((e1, e2) -> e2.getValue().compareTo(e1.getValue()))
                .forEach(entry -> {
                    System.out.println(
                            "  " + entry.getKey() + ": " + entry.getValue() + " overlap courses");
                });

        return suggestions;
    }

    // ========== Utility Method 3: Print Detailed Requirements ==========

    /**
     * Print detailed breakdown of requirements for double major
     * 
     * @param major1     First major
     * @param major2     Second major
     * @param allCourses List of all courses
     */
    public static void printDetailedRequirements(String major1, String major2,
            List<Course> allCourses) {
        List<String> major1Reqs = getRequiredCourses(major1);
        List<String> major2Reqs = getRequiredCourses(major2);
        List<String> merged = mergeRequirements(major1, major2, allCourses);

        System.out.println("\n========== Detailed Requirements ==========");

        // Major 1 only courses
        System.out.println("\n" + major1 + " only courses:");
        for (String courseId : major1Reqs) {
            if (!major2Reqs.contains(courseId)) {
                Course c = findCourse(allCourses, courseId);
                if (c != null) {
                    System.out.println("  • " + c.getCourseId() + ": " + c.getName() + " ("
                            + c.getCredits() + " credits)");
                }
            }
        }

        // Major 2 only courses
        System.out.println("\n" + major2 + " only courses:");
        for (String courseId : major2Reqs) {
            if (!major1Reqs.contains(courseId)) {
                Course c = findCourse(allCourses, courseId);
                if (c != null) {
                    System.out.println("  • " + c.getCourseId() + ": " + c.getName() + " ("
                            + c.getCredits() + " credits)");
                }
            }
        }

        // Overlap courses
        System.out.println("\nOverlap courses (count for both):");
        for (String courseId : major1Reqs) {
            if (major2Reqs.contains(courseId)) {
                Course c = findCourse(allCourses, courseId);
                if (c != null) {
                    System.out.println("  ⭐ " + c.getCourseId() + ": " + c.getName() + " ("
                            + c.getCredits() + " credits)");
                }
            }
        }
    }

    // ========== Helper Method: Find Course by ID ==========

    /**
     * Find a course object by its ID
     * 
     * @param allCourses List of all courses
     * @param courseId   Course ID to find
     * @return Course object if found, null otherwise
     */
    private static Course findCourse(List<Course> allCourses, String courseId) {
        for (Course c : allCourses) {
            if (c.getCourseId().equals(courseId)) {
                return c;
            }
        }
        return null;
    }

    // ========== Utility Method 4: Calculate Workload ==========

    /**
     * Calculate average workload per semester for double major
     * 
     * @param requiredCourses List of required courses
     * @param allCourses      List of all courses
     * @return Average credits per semester
     */
    public static double calculateAverageWorkload(List<String> requiredCourses,
            List<Course> allCourses) {
        int totalCredits = calculateTotalCredits(requiredCourses, allCourses);
        return totalCredits / 8.0; // 8 semesters
    }

    // ========== Utility Method 5: Priority Score for Overlap Courses ==========

    /**
     * Calculate priority score for a course in double major context Overlap courses
     * get higher priority
     * 
     * @param course The course
     * @param majors List of student's majors
     * @return Priority score (higher = more important)
     */
    public static int calculateCoursePriority(Course course, List<String> majors) {
        int priority = 0;

        // Base priority: how many majors does this course satisfy?
        for (String major : majors) {
            if (course.belongsToMajor(major)) {
                priority += 100; // +100 for each major it satisfies
            }
        }

        // Bonus for being an overlap course
        if (course.isOverlapCourse(majors)) {
            priority += 50; // Extra bonus for overlap
        }

        return priority;
    }
}
