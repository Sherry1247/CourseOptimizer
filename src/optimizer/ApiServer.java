package optimizer;

import com.sun.net.httpserver.HttpServer;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpHandler;

import models.*;
import graph.PrerequisiteGraph;

import java.io.*;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.*;

public class ApiServer {

    public static void start() throws IOException {
        HttpServer server = HttpServer.create(new InetSocketAddress(8080), 0);

        server.createContext("/generate-plan", new GeneratePlanHandler());
        server.setExecutor(null);

        System.out.println("API server running on http://localhost:8080");
        server.start();
    }

    // =======================
    // Handler: Generate Plan
    // =======================
    static class GeneratePlanHandler implements HttpHandler {
        @Override
        public void handle(HttpExchange exchange) throws IOException {

            if (!exchange.getRequestMethod().equalsIgnoreCase("POST")) {
                sendResponse(exchange, 405, "Method Not Allowed");
                return;
            }

            // Read JSON body from frontend
            String body = new String(exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8);

            // Convert JSON → Java objects (你可以用 minimal JSON parser 或 org.json)
            Map<String, Object> json = Json.parse(body);

            StudentProfile profile = Json.toStudentProfile(json);
            List<Course> allCourses = CourseRepository.loadAllCourses();

            ScheduleOptimizer optimizer = new ScheduleOptimizer();
            List<Semester> plan = optimizer.generatePlan(profile, allCourses);

            String jsonResponse = Json.planToJson(plan);
            sendResponse(exchange, 200, jsonResponse);
        }
    }

    private static void sendResponse(HttpExchange exchange, int status, String text) throws IOException {
        byte[] bytes = text.getBytes(StandardCharsets.UTF_8);
        exchange.sendResponseHeaders(status, bytes.length);
        OutputStream os = exchange.getResponseBody();
        os.write(bytes);
        os.close();
    }
}
