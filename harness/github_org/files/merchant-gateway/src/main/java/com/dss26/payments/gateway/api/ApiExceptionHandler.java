package com.dss26.payments.gateway.api;

import java.util.Map;

import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

import com.dss26.payments.gateway.events.PublishFailedException;

/**
 * Every error leaves the gateway as application/problem+json with a stable
 * {@code code} that acquirers can switch on.
 */
@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(MethodArgumentNotValidException.class)
    ResponseEntity<ProblemDetail> invalid(MethodArgumentNotValidException e) {
        ProblemDetail problem = problem(HttpStatus.BAD_REQUEST, "validation_failed", "Request failed validation");
        problem.setProperty("errors", e.getBindingResult().getFieldErrors().stream()
                .map(error -> Map.of("field", error.getField(), "message", String.valueOf(error.getDefaultMessage())))
                .toList());
        return ResponseEntity.badRequest().body(problem);
    }

    @ExceptionHandler(AuthorisationRejectedException.class)
    ResponseEntity<ProblemDetail> rejected(AuthorisationRejectedException e) {
        ResponseEntity.BodyBuilder response = ResponseEntity.status(e.status());
        if (e.status() == HttpStatus.TOO_MANY_REQUESTS) {
            response.header(HttpHeaders.RETRY_AFTER, "1");
        }
        return response.body(problem(e.status(), e.code(), e.getMessage()));
    }

    @ExceptionHandler(PublishFailedException.class)
    ResponseEntity<ProblemDetail> publishFailed(PublishFailedException e) {
        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE).body(problem(HttpStatus.SERVICE_UNAVAILABLE,
                "publish_failed", "Authorisation was not queued; it is safe to retry"));
    }

    private static ProblemDetail problem(HttpStatus status, String code, String detail) {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(status, detail);
        problem.setProperty("code", code);
        return problem;
    }
}
