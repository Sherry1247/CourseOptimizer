package models;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

/**
 * Student Profile class - Stores student preferences and goals
 * 
 * Includes: - Major information (with double major support) - Academic goals
 * (GPA target, max credits) - Time preferences (no early classes) - Strategy
 * preferences (prioritize GPA, balance difficulty) - Career goals (grad school
 * or industry)
 */
public class StudentProfile {
    // ========== Basic Information ==========
    private String major; // Primary major, e.g., "CS"
    private String secondMajor; // Second major for double major, e.g., "MATH" (optional)

    // ========== Academic Goals ==========
    private double gpaGoal; // Target GPA, e.g., 3.5
    private int maxCreditsPerSem; // Maximum credits per semester, e.g., 15

    // ========== Time Preferences ==========
    private boolean noEarlyClass; // Avoid 8am classes, true/false

    // ========== Strategy Preferences ==========
    private boolean prioritizeGPA; // Prioritize easier courses for higher GPA
    private boolean balanceDifficulty; // Balance difficulty across semesters

    // ========== Career Goals ==========
    private String careerGoal; // "grad_school" or "industry"
    
    private boolean doubleMajorFlag;
    private Set<String> completedCourses;

    // ========== Constructors ==========

    /**
     * Default constructor with reasonable defaults
     */
    public StudentProfile() {
        this.maxCreditsPerSem = 15;
        this.gpaGoal = 3.0;
        this.noEarlyClass = false;
        this.prioritizeGPA = false;
        this.balanceDifficulty = true; // Enable difficulty balancing by default
        this.careerGoal = "industry";
        this.secondMajor = null; // No double major by default
        this.doubleMajorFlag = false;
        this.completedCourses = new HashSet<>();
    }

    /**
     * Constructor with basic parameters
     */
    public StudentProfile(String major, double gpaGoal, int maxCreditsPerSem, boolean noEarlyClass,
            boolean prioritizeGPA, String careerGoal) {
        this.major = major;
        this.gpaGoal = gpaGoal;
        this.maxCreditsPerSem = maxCreditsPerSem;
        this.noEarlyClass = noEarlyClass;
        this.prioritizeGPA = prioritizeGPA;
        this.balanceDifficulty = true;
        this.careerGoal = careerGoal;
        this.secondMajor = null;
        this.doubleMajorFlag = false;
        this.completedCourses = new HashSet<>();
    }

    // ========== Getters and Setters ==========

    public String getMajor() {
        return major;
    }

    public void setMajor(String major) {
        this.major = major;
    }

    public String getSecondMajor() {
        return secondMajor;
    }

    public void setSecondMajor(String secondMajor) {
        this.secondMajor = secondMajor;
    }

    public double getGpaGoal() {
        return gpaGoal;
    }

    public void setGpaGoal(double gpaGoal) {
        this.gpaGoal = gpaGoal;
    }

    public int getMaxCreditsPerSem() {
        return maxCreditsPerSem;
    }

    public void setMaxCreditsPerSem(int maxCreditsPerSem) {
        this.maxCreditsPerSem = maxCreditsPerSem;
    }

    public boolean isNoEarlyClass() {
        return noEarlyClass;
    }

    public void setNoEarlyClass(boolean noEarlyClass) {
        this.noEarlyClass = noEarlyClass;
    }

    public boolean isPrioritizeGPA() {
        return prioritizeGPA;
    }

    public void setPrioritizeGPA(boolean prioritizeGPA) {
        this.prioritizeGPA = prioritizeGPA;
    }

    public boolean isBalanceDifficulty() {
        return balanceDifficulty;
    }

    public void setBalanceDifficulty(boolean balanceDifficulty) {
        this.balanceDifficulty = balanceDifficulty;
    }

    public String getCareerGoal() {
        return careerGoal;
    }

    public void setCareerGoal(String careerGoal) {
        this.careerGoal = careerGoal;
    }
    
 // ===== Double Major Flag =====
    public void setDoubleMajor(boolean flag) {
        this.doubleMajorFlag = flag;
    }

    public boolean isDoubleMajorFlag() {
        return this.doubleMajorFlag;
    }

    // ===== Completed Courses =====
    public void setCompletedCourses(Set<String> completed) {
        if (completed == null) completed = new HashSet<>();
        this.completedCourses = completed;
    }

    public Set<String> getCompletedCourses() {
        return this.completedCourses;
    }

    // ========== Utility Methods ==========

    /**
     * Check if student has a double major
     * 
     * @return true if has second major, false otherwise
     */
    public boolean hasDoubleMajor() {
        return secondMajor != null && !secondMajor.isEmpty();
    }

    /**
     * Get all majors (both primary and second if exists)
     * 
     * @return List of major names
     */
    public List<String> getAllMajors() {
        List<String> majors = new ArrayList<>();
        majors.add(major);
        if (hasDoubleMajor()) {
            majors.add(secondMajor);
        }
        return majors;
    }

    /**
     * Validate if profile configuration is valid
     * 
     * @return true if valid, false otherwise
     */
    public boolean isValid() {
        return major != null && !major.isEmpty() && gpaGoal >= 0.0 && gpaGoal <= 4.0
                && maxCreditsPerSem >= 12 && maxCreditsPerSem <= 21;
    }

    /**
     * Get a summary of the student's preferences
     */
    public String getPreferencesSummary() {
        StringBuilder sb = new StringBuilder();
        sb.append("Student Preferences:\n");
        sb.append("  Major(s): ").append(hasDoubleMajor() ? major + " + " + secondMajor : major)
                .append("\n");
        sb.append("  GPA Goal: ").append(gpaGoal).append("\n");
        sb.append("  Max Credits/Semester: ").append(maxCreditsPerSem).append("\n");
        sb.append("  No Early Classes: ").append(noEarlyClass ? "Yes" : "No").append("\n");
        sb.append("  Prioritize GPA: ").append(prioritizeGPA ? "Yes" : "No").append("\n");
        sb.append("  Balance Difficulty: ").append(balanceDifficulty ? "Yes" : "No").append("\n");
        sb.append("  Career Goal: ").append(careerGoal);
        return sb.toString();
    }

    /**
     * toString method for easy debugging
     */
    @Override
    public String toString() {
        String majorStr = hasDoubleMajor() ? major + " + " + secondMajor : major;
        return String.format(
                "Student[major=%s, GPA goal=%.1f, max credits=%d, balance difficulty=%s, career=%s]",
                majorStr, gpaGoal, maxCreditsPerSem, balanceDifficulty, careerGoal);
    }
}