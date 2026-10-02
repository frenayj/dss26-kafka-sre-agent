package com.dss26.cards.lifecycle.card

import com.dss26.cards.events.ActivationChannel
import com.dss26.cards.events.BlockInitiator
import com.dss26.cards.events.BlockReason
import com.dss26.cards.events.CardActivated
import com.dss26.cards.events.CardBlocked
import com.dss26.cards.events.CardFormFactor
import com.dss26.cards.events.CardIssued
import com.dss26.cards.events.CardReplaced
import com.dss26.cards.events.ReplacementReason
import com.dss26.cards.lifecycle.events.Outbox
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Transactional
import java.time.Clock

@Service
class CardService(
    private val cards: CardRepository,
    private val outbox: Outbox,
    private val clock: Clock,
) {

    @Transactional
    fun issue(cardToken: String, customerId: String, productCode: String, formFactor: CardFormFactor,
              bin: String, expiryYyyymm: String): Card {
        val now = clock.instant()
        val card = Card(cardToken, customerId, productCode, formFactor, bin, expiryYyyymm,
            CardStateMachine.initialState(formFactor), null, now)
        cards.insert(card)
        outbox.add(cardToken, CardIssued.newBuilder()
            .setCardToken(cardToken)
            .setCustomerId(customerId)
            .setProductCode(productCode)
            .setFormFactor(formFactor)
            .setBin(bin)
            .setExpiryYyyymm(expiryYyyymm)
            .setIssuedAt(now)
            .build())
        return card
    }

    @Transactional
    fun activate(cardToken: String, channel: ActivationChannel): Card {
        val card = load(cardToken)
        val updated = card.copy(state = CardStateMachine.activate(card.state), updatedAt = clock.instant())
        cards.updateState(updated)
        outbox.add(cardToken, CardActivated.newBuilder()
            .setCardToken(cardToken)
            .setCustomerId(card.customerId)
            .setActivationChannel(channel)
            .setActivatedAt(updated.updatedAt)
            .build())
        return updated
    }

    @Transactional
    fun block(cardToken: String, reason: BlockReason, initiator: BlockInitiator): Card {
        val card = load(cardToken)
        if (card.state == CardState.BLOCKED && card.blockReason == reason) return card
        val updated = card.copy(state = CardStateMachine.block(card.state), blockReason = reason,
            updatedAt = clock.instant())
        cards.updateState(updated)
        outbox.add(cardToken, CardBlocked.newBuilder()
            .setCardToken(cardToken)
            .setCustomerId(card.customerId)
            .setBlockReason(reason)
            .setInitiator(initiator)
            .setBlockedAt(updated.updatedAt)
            .build())
        return updated
    }

    @Transactional
    fun replace(oldToken: String, newToken: String, reason: ReplacementReason, expiryYyyymm: String): Card {
        val old = load(oldToken)
        val now = clock.instant()
        cards.updateState(old.copy(state = CardStateMachine.replace(old.state), updatedAt = now))
        val replacement = issue(newToken, old.customerId, old.productCode, old.formFactor, old.bin, expiryYyyymm)
        outbox.add(oldToken, CardReplaced.newBuilder()
            .setOldCardToken(oldToken)
            .setNewCardToken(newToken)
            .setCustomerId(old.customerId)
            .setReplacementReason(reason)
            .setReplacedAt(now)
            .build())
        return replacement
    }

    fun find(cardToken: String): Card? = cards.find(cardToken)

    private fun load(cardToken: String): Card =
        cards.findForUpdate(cardToken) ?: throw NoSuchElementException("Unknown card $cardToken")
}
