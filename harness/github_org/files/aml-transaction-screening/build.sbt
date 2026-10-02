ThisBuild / scalaVersion := "2.13.15"
ThisBuild / organization := "com.dss26.aml"

lazy val kafkaVersion = "3.8.1"
lazy val confluentVersion = "7.8.0"

lazy val root = (project in file("."))
  .settings(
    name := "aml-transaction-screening",
    resolvers += "confluent" at "https://packages.confluent.io/maven/",
    libraryDependencies ++= Seq(
      "org.apache.kafka" %% "kafka-streams-scala" % kafkaVersion,
      "io.confluent" % "kafka-streams-avro-serde" % confluentVersion,
      "com.typesafe" % "config" % "1.4.3",
      "ch.qos.logback" % "logback-classic" % "1.5.12",
      "org.scalatest" %% "scalatest" % "3.2.19" % Test,
      "org.apache.kafka" % "kafka-streams-test-utils" % kafkaVersion % Test
    ),
    scalacOptions ++= Seq("-deprecation", "-feature", "-Xfatal-warnings"),
    assembly / mainClass := Some("com.dss26.aml.screening.Main"),
    assembly / assemblyMergeStrategy := {
      case PathList("META-INF", "services", _*) => MergeStrategy.concat
      case PathList("META-INF", _*)             => MergeStrategy.discard
      case _                                    => MergeStrategy.first
    }
  )
