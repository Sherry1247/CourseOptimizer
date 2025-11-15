package optimizer;

import models.*;
import graph.PrerequisiteGraph;
import scorer.CourseScorer;
import java.util.*;

/**
 * Schedule Optimizer - Core algorithm for generating 4-year course plans
 * 
 * Main Functions: 1. Generate optimal 4-year plan based on student preferences
 * 2. Respect prerequisite constraints 3. Optimize for GPA, professor ratings,
 * and relevance 4. Support double major planning 5. Balance difficulty across
 * semesters
 */
public class ScheduleOptimizer {
    // ========== Instance Variables ==========
    private PrerequisiteGraph prereqGraph;

    // ========== Constructor ==========

    public ScheduleOptimizer() {
        this.prereqGraph = new PrerequisiteGraph();
    }

    // ========== Core Method: Generate 4-Year Plan ==========

    /**
     * Generate complete 4-year plan with double major support
     * 
     * This is the main entry point for the optimizer
     * 
     * @param profile    Student profile (preferences, goals, major(s))
     * @param allCourses List of all available courses
     * @return List of 8 semesters with optimized course schedules
     */
    public List<Semester> generatePlan(StudentProfile profile, List<Course> allCourses) {

        // 1. Build prerequisite graph
        prereqGraph.addCourses(allCourses);

        // Check for circular dependencies
        if (prereqGraph.hasCycle()) {
            System.err.println("️ Warning: Prerequisite graph has circular dependencies!");
        }

        // 2. Get required courses based on major(s)
        List<String> requiredCourses;

        if (profile.hasDoubleMajor()) {
            // Double major: merge requirements from both majors
            System.out.println("\n Planning for double major: " + profile.getMajor() + " + "
                    + profile.getSecondMajor());

            requiredCourses = DoubleMajorHelper.mergeRequirements(profile.getMajor(),
                    profile.getSecondMajor(), allCourses);

            // Check feasibility
            boolean feasible = DoubleMajorHelper.isFeasible(requiredCourses, allCourses,
                    profile.getMaxCreditsPerSem());

            if (!feasible) {
                System.err.println(" Warning: Double major may not be feasible in 4 years!");
            }
        } else {
            // Single major
            System.out.println("\n Planning for major: " + profile.getMajor());
            requiredCourses = DoubleMajorHelper.getRequiredCourses(profile.getMajor());
        }

        System.out.println("Total courses required: " + requiredCourses.size());

        // 3. Generate the plan
        List<Semester> plan = generatePlanInternal(profile, allCourses, requiredCourses);

        // 4. Balance difficulty if enabled
        if (profile.isBalanceDifficulty()) {
            System.out.println("\n⚖️ Balancing difficulty across semesters...");
            DifficultyBalancer.balancePlan(plan);
        }

        // 5. Analyze difficulty
        DifficultyBalancer.analyzeDifficulty(plan);

        return plan;
    }

    // ========== Internal Generation Logic ==========

    /**
     * Internal method to generate the plan Uses greedy algorithm with scoring
     * system
     * 
     * @param profile         Student profile
     * @param allCourses      All available courses
     * @param requiredCourses List of required course IDs
     * @return List of 8 semesters
     */
    private List<Semester> generatePlanInternal(StudentProfile profile, List<Course> allCourses,
            List<String> requiredCourses) {
        // Create 8 empty semesters
        List<Semester> plan = createEmptySemesters();

        // Track state
        Set<String> completedCourses = new HashSet<>(); // Courses already scheduled
        Set<String> remainingCourses = new HashSet<>(requiredCourses); // Courses still needed

        System.out.println("\n Generating semester-by-semester plan...\n");

        // Fill each semester
        for (int i = 0; i < plan.size(); i++) {
            Semester semester = plan.get(i);

            System.out.println("Planning " + semester.getSemesterLabel() + "...");

            fillSemester(semester, profile, completedCourses, remainingCourses, allCourses);

            System.out.println("  ✓ Added " + semester.getCourseCount() + " courses ("
                    + semester.getTotalCredits() + " credits)");
        }

        // Check if all required courses were scheduled
        if (!remainingCourses.isEmpty()) {
            System.err.println("\n Warning: Could not fit all required courses!");
            System.err.println("Missing courses: " + remainingCourses);
            System.err.println("Suggestions:");
            System.err.println("  1. Increase max credits per semester");
            System.err.println("  2. Take summer courses");
            System.err.println("  3. Extend to 5 years");
        } else {
            System.out.println("\n All required courses scheduled successfully!");
        }

        return plan;
    }

    // ========== Helper Method: Create Empty Semesters ==========

    /**
     * Create 8 empty semesters (4 years)
     * 
     * @return List of 8 empty Semester objects
     */
    private List<Semester> createEmptySemesters() {
        List<Semester> semesters = new ArrayList<>();

        for (int year = 1; year <= 4; year++) {
            semesters.add(new Semester(year, "Fall"));
            semesters.add(new Semester(year, "Spring"));
        }

        return semesters;
    }

    // ========== Helper Method: Fill One Semester ==========

    /**
     * Fill a single semester with courses using greedy algorithm
     * 
     * Strategy: 1. Get all courses that can be taken (prerequisites satisfied) 2.
     * Filter out courses that don't meet basic requirements 3. Score each course
     * based on student preferences 4. Sort by score (highest first) 5. Greedily add
     * courses until credit limit reached
     * 
     * @param semester         The semester to fill
     * @param profile          Student profile
     * @param completedCourses Set of already completed courses
     * @param remainingCourses Set of courses still needed
     * @param allCourses       List of all available courses
     */
    private void fillSemester(Semester semester, StudentProfile profile,
            Set<String> completedCourses, Set<String> remainingCourses, List<Course> allCourses) {

        int maxCredits = profile.getMaxCreditsPerSem();
        int currentCredits = 0;

        // 1. Get courses that are available to take (prerequisites satisfied)
        List<String> availableCourseIds = prereqGraph.getAvailableCourses(completedCourses,
                remainingCourses);

        if (availableCourseIds.isEmpty()) {
            return; // No courses available for this semester
        }

        // 2. Convert to Course objects and filter
        List<Course> availableCourses = new ArrayList<>();
        for (String courseId : availableCourseIds) {
            Course course = prereqGraph.getCourse(courseId);

            // Filter: only include courses that meet basic requirements
            if (course != null && CourseScorer.meetsBasicRequirements(course, profile)) {
                availableCourses.add(course);
            }
        }

        if (availableCourses.isEmpty()) {
            return; // No suitable courses after filtering
        }

        // 3. Sort courses by priority
        sortCoursesByPriority(availableCourses, profile);

        // 4. Greedily add courses
        for (Course course : availableCourses) {
            int courseCredits = course.getCredits();

            // Check if adding this course would exceed credit limit
            if (currentCredits + courseCredits <= maxCredits) {
                // Add course to semester
                semester.addCourse(course);
                currentCredits += courseCredits;

                // Update state
                completedCourses.add(course.getCourseId());
                remainingCourses.remove(course.getCourseId());

                System.out.println("    + " + course.getCourseId() + ": " + course.getName() + " ("
                        + courseCredits + " credits)");
            }

            // Stop if credit limit reached
            if (currentCredits >= maxCredits) {
                break;
            }
        }
    }

    // ========== Helper Method: Sort Courses by Priority ==========

    /**
     * Sort courses by priority for greedy selection
     * 
     * Priority factors: 1. Overlap courses (for double major) - highest priority 2.
     * Course score (from CourseScorer) 3. Prerequisite for other courses (unlock
     * more courses)
     * 
     * @param courses List of courses to sort (modified in place)
     * @param profile Student profile
     */
    private void sortCoursesByPriority(List<Course> courses, StudentProfile profile) {
        courses.sort((c1, c2) -> {
            // Factor 1: Overlap courses (for double major)
            if (profile.hasDoubleMajor()) {
                boolean c1Overlap = c1.isOverlapCourse(profile.getAllMajors());
                boolean c2Overlap = c2.isOverlapCourse(profile.getAllMajors());

                if (c1Overlap && !c2Overlap)
                    return -1; // c1 has higher priority
                if (!c1Overlap && c2Overlap)
                    return 1; // c2 has higher priority
            }

            // Factor 2: Course score
            double score1 = CourseScorer.scoreCourse(c1, profile);
            double score2 = CourseScorer.scoreCourse(c2, profile);

            // Sort by score (descending - higher score first)
            return Double.compare(score2, score1);
        });
    }

    // ========== Utility Method: Print Plan Statistics ==========

    /**
     * Print comprehensive statistics about the generated plan
     * 
     * @param plan List of semesters
     */
    public void printPlanStatistics(List<Semester> plan) {
        System.out.println("\n========== Plan Statistics ==========");
        System.out.println("=".repeat(60));

        int totalCredits = 0;
        double totalGPA = 0.0;
        int semesterCount = 0;
        int totalCourses = 0;

        // Print each semester
        for (Semester semester : plan) {
            if (semester.getCourseCount() == 0) {
                continue; // Skip empty semesters
            }

            totalCredits += semester.getTotalCredits();
            totalGPA += semester.getExpectedGPA();
            totalCourses += semester.getCourseCount();
            semesterCount++;

            double avgDiff = DifficultyBalancer.calculateAverageDifficulty(semester);

            System.out.printf("%s: %d credits, GPA %.2f, Difficulty %.1f, %d courses%n",
                    semester.getSemesterLabel(), semester.getTotalCredits(),
                    semester.getExpectedGPA(), avgDiff, semester.getCourseCount());
        }

        System.out.println("=".repeat(60));

        // Overall statistics
        System.out.printf("Total credits: %d over %d semesters%n", totalCredits, semesterCount);
        System.out.printf("Total courses: %d%n", totalCourses);
        System.out.printf("Average GPA: %.2f%n",
                semesterCount > 0 ? totalGPA / semesterCount : 0.0);
        System.out.printf("Average credits per semester: %.1f%n",
                semesterCount > 0 ? (double) totalCredits / semesterCount : 0.0);

        // Difficulty balance
        String balanceQuality = DifficultyBalancer.checkBalanceQuality(plan);
        System.out.printf("Difficulty balance: %s%n", balanceQuality);
    }

    // ========== Utility Method: Print Detailed Plan ==========

    /**
     * Print detailed view of the entire plan Shows all courses in each semester
     * with their details
     * 
     * @param plan List of semesters
     */
    public void printDetailedPlan(List<Semester> plan) {
        System.out.println("\n========== Detailed 4-Year Plan ==========\n");

        for (Semester semester : plan) {
            if (semester.getCourseCount() == 0) {
                continue;
            }

            System.out.println(semester.getDetailedSummary());
        }
    }

    // ========== Advanced Optimization Methods ==========

    /**
     * Optimize plan for maximum GPA Adjusts course selection to prioritize easier
     * courses
     * 
     * @param plan    Current plan
     * @param profile Student profile
     */
    public void optimizeForGPA(List<Semester> plan, StudentProfile profile) {
        double targetGPA = profile.getGpaGoal();

        System.out.println("\n Optimizing for GPA target: " + targetGPA);

        for (Semester semester : plan) {
            if (semester.getExpectedGPA() < targetGPA - 0.2) {
                System.out.println(semester.getSemesterLabel() + " GPA ("
                        + String.format("%.2f", semester.getExpectedGPA()) + ") is below target");
                // TODO: Implement course swapping to improve GPA
            }
        }
    }

    /**
     * Check if plan meets graduation requirements
     * 
     * @param plan            The plan to check
     * @param requiredCourses List of required course IDs
     * @return true if all requirements met, false otherwise
     */
    public boolean meetsGraduationRequirements(List<Semester> plan, List<String> requiredCourses) {
        Set<String> scheduledCourses = new HashSet<>();

        for (Semester semester : plan) {
            for (Course course : semester.getCourses()) {
                scheduledCourses.add(course.getCourseId());
            }
        }

        return scheduledCourses.containsAll(requiredCourses);
    }

    /**
     * Get list of semesters that are too heavy (too many credits)
     * 
     * @param plan      The plan
     * @param threshold Credit threshold
     * @return List of overloaded semesters
     */
    public List<Semester> findOverloadedSemesters(List<Semester> plan, int threshold) {
        List<Semester> overloaded = new ArrayList<>();

        for (Semester semester : plan) {
            if (semester.getTotalCredits() > threshold) {
                overloaded.add(semester);
            }
        }

        return overloaded;
    }

    /**
     * Calculate total estimated study time for the plan Assumes 3 hours of work per
     * credit hour
     * 
     * @param plan The plan
     * @return Total hours
     */
    public int calculateTotalStudyHours(List<Semester> plan) {
        int totalCredits = 0;

        for (Semester semester : plan) {
            totalCredits += semester.getTotalCredits();
        }

        return totalCredits * 3; // 3 hours per credit
    }

    /**
     * Generate summary report
     * 
     * @param plan    The plan
     * @param profile Student profile
     * @return Summary string
     */
    public String generateSummaryReport(List<Semester> plan, StudentProfile profile) {
        StringBuilder report = new StringBuilder();

        report.append("========== Course Plan Summary ==========\n");
        report.append("Student: ").append(profile.getMajor());
        if (profile.hasDoubleMajor()) {
            report.append(" + ").append(profile.getSecondMajor());
        }
        report.append("\n");
        report.append("GPA Goal: ").append(profile.getGpaGoal()).append("\n");
        report.append("\n");

        int totalCredits = 0;
        double totalGPA = 0.0;
        int semCount = 0;

        for (Semester sem : plan) {
            if (sem.getCourseCount() > 0) {
                totalCredits += sem.getTotalCredits();
                totalGPA += sem.getExpectedGPA();
                semCount++;
            }
        }

        report.append("Total Credits: ").append(totalCredits).append("\n");
        report.append("Expected Average GPA: ")
                .append(String.format("%.2f", semCount > 0 ? totalGPA / semCount : 0.0))
                .append("\n");
        report.append("Difficulty Balance: ").append(DifficultyBalancer.checkBalanceQuality(plan))
                .append("\n");

        return report.toString();
    }
}