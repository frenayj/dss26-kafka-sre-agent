package com.dss26.kyc.onboarding.events

import com.dss26.kyc.events.CustomerRiskRating
import com.dss26.kyc.events.KycMethod
import com.dss26.kyc.events.KycOutcome
import com.dss26.kyc.events.KycVerificationCompleted
import com.dss26.kyc.onboarding.verification.VerificationResult
import org.apache.avro.specific.SpecificRecord
import org.springframework.kafka.core.KafkaTemplate
import org.springframework.stereotype.Component
import org.springframework.transaction.support.TransactionSynchronization
import org.springframework.transaction.support.TransactionSynchronizationManager

/**
 * kyc.verification.completed.v1, keyed by customer. Sent after the database
 * commit: customer-profile-svc opens the account from this event, so it must
 * never announce a verification we rolled back.
 */
@Component
class KycEventPublisher(private val kafka: KafkaTemplate<String, SpecificRecord>) {

    fun verificationCompleted(result: VerificationResult) {
        val event = KycVerificationCompleted.newBuilder()
            .setCustomerId(result.customerId)
            .setKycReference(result.kycReference)
            .setMethod(KycMethod.valueOf(result.method.name))
            .setOutcome(KycOutcome.valueOf(result.outcome.name))
            .setRiskRating(CustomerRiskRating.valueOf(result.riskRating.name))
            .setExpiresAt(result.expiresAt)
            .setVerifiedAt(result.verifiedAt)
            .build()
        TransactionSynchronizationManager.registerSynchronization(object : TransactionSynchronization {
            override fun afterCommit() {
                kafka.send(TOPIC, result.customerId, event)
            }
        })
    }

    companion object {
        const val TOPIC = "kyc.verification.completed.v1"
    }
}
