package graph;

import models.Course;
import java.util.*;

public class PrerequisiteGraph {
    // 邻接表：courseId -> 它的所有prerequisite
    private Map<String, List<String>> graph;
    private Map<String, Course> courseMap;

    public PrerequisiteGraph() {
        this.graph = new HashMap<>();
        this.courseMap = new HashMap<>();
    }

    // 添加课程和它的prerequisites
    public void addCourse(Course course) {
        String courseId = course.getCourseId();

        // 存储课程对象
        courseMap.put(courseId, course); // ✅ 添加这行

        // 添加prerequisite边
        List<String> prereqs = course.getPrerequisites();
        if (prereqs != null) {
            graph.put(courseId, new ArrayList<>(prereqs));
        } else {
            graph.put(courseId, new ArrayList<>());
        }
    }

    public void addCourses(List<Course> courses) {
        for (Course c : courses) {
            addCourse(c);
        }
    }

    public boolean hasCycle() {
        Set<String> visiting = new HashSet<>();
        Set<String> visited = new HashSet<>();

        for (String courseId : graph.keySet()) {
            if (dfsHasCycle(courseId, visiting, visited)) {
                return true;
            }
        }

        return false;
    }

    private boolean dfsHasCycle(String node, Set<String> visiting, Set<String> visited) {

        if (visited.contains(node))
            return false;
        if (visiting.contains(node))
            return true; // 回到正在访问的节点 = 有环

        visiting.add(node);

        for (String prereq : graph.getOrDefault(node, new ArrayList<>())) {
            if (dfsHasCycle(prereq, visiting, visited)) {
                return true;
            }
        }

        visiting.remove(node);
        visited.add(node);

        return false;
    }

    public Course getCourse(String courseId) {
        return courseMap.get(courseId);
    }

    // 检查是否可以选这门课
    public boolean canTake(String courseId, Set<String> completedCourses) {
        List<String> prereqs = graph.get(courseId);

        if (prereqs == null || prereqs.isEmpty()) {
            return true; // 没有prerequisite
        }

        // 所有prerequisite都修完了才能选
        return completedCourses.containsAll(prereqs);
    }

    // 获取当前可选的所有课程
    public List<String> getAvailableCourses(Set<String> completedCourses,
            Set<String> remainingCourses) {
        List<String> available = new ArrayList<>();

        for (String courseId : remainingCourses) {
            // 如果所有 prerequisite 都修了，就可以选
            if (canTake(courseId, completedCourses)) {
                available.add(courseId);
            }
        }

        return available;
    }

    // 拓扑排序：返回合理的课程顺序
    public List<String> topologicalSort() {
        // TODO: 你来实现！（BFS或DFS）
        // 这个可以用来检测是否有循环依赖
        return new ArrayList<>();
    }
}
