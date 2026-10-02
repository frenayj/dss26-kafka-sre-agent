package com.dss26.kyc.onboarding

import org.springframework.boot.autoconfigure.SpringBootApplication
import org.springframework.boot.runApplication
import org.springframework.scheduling.annotation.EnableScheduling

@SpringBootApplication
@EnableScheduling
class KycOnboardingApplication

fun main(args: Array<String>) {
    runApplication<KycOnboardingApplication>(*args)
}
