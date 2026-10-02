package com.dss26.cards.lifecycle.card

import com.dss26.cards.events.BlockReason
import com.dss26.cards.events.CardFormFactor

enum class CardState { ISSUED, ACTIVE, BLOCKED, REPLACED }

class IllegalCardTransition(from: CardState, action: String) :
    IllegalStateException("Cannot $action a card in state $from")

/**
 * The only place that decides which lifecycle transitions are legal. Every
 * transition emits exactly one cards.card.* event through the outbox.
 */
object CardStateMachine {

    /** Virtual and tokenised cards are usable as soon as they exist; plastic waits for activation. */
    fun initialState(formFactor: CardFormFactor): CardState =
        if (formFactor == CardFormFactor.PHYSICAL) CardState.ISSUED else CardState.ACTIVE

    fun activate(from: CardState): CardState = when (from) {
        CardState.ISSUED -> CardState.ACTIVE
        else -> throw IllegalCardTransition(from, "activate")
    }

    fun block(from: CardState): CardState = when (from) {
        CardState.ISSUED, CardState.ACTIVE -> CardState.BLOCKED
        CardState.BLOCKED -> CardState.BLOCKED
        CardState.REPLACED -> throw IllegalCardTransition(from, "block")
    }

    /** Only a customer freeze can be lifted; lost, stolen and fraud blocks end in a replacement. */
    fun unblock(from: CardState, reason: BlockReason): CardState = when {
        from == CardState.BLOCKED && reason == BlockReason.CUSTOMER_REQUEST -> CardState.ACTIVE
        else -> throw IllegalCardTransition(from, "unblock")
    }

    fun replace(from: CardState): CardState = when (from) {
        CardState.ACTIVE, CardState.BLOCKED -> CardState.REPLACED
        else -> throw IllegalCardTransition(from, "replace")
    }
}
