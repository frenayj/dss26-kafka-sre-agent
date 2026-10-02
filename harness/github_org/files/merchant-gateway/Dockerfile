FROM eclipse-temurin:21-jre

RUN groupadd --system gateway && useradd --system --gid gateway gateway
WORKDIR /app
COPY target/merchant-gateway.jar app.jar
USER gateway

EXPOSE 8080
ENTRYPOINT ["java", "-XX:MaxRAMPercentage=75", "-jar", "/app/app.jar"]
