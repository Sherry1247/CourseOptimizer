import optimizer.ApiServer;

public class ApiMain {
    public static void main(String[] args) {
        System.out.println("Starting CourseOptimizer API server...");
        try {
            ApiServer.start();
        } catch (Exception e) {
            e.printStackTrace();
        }
    }
}
