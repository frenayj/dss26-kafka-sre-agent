package com.dss26.cards.lifecycle.card

import com.dss26.cards.events.BlockReason
import com.dss26.cards.events.CardFormFactor
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.assertThrows
import kotlin.test.assertEquals

class CardStateMachineTest {

    @Test
    fun `plastic cards wait for activation, virtual cards do not`() {
        assertEquals(CardState.ISSUED, CardStateMachine.initialState(CardFormFactor.PHYSICAL))
        assertEquals(CardState.ACTIVE, CardStateMachine.initialState(CardFormFactor.VIRTUAL))
        assertEquals(CardState.ACTIVE, CardStateMachine.initialState(CardFormFactor.TOKENISED))
    }

    @Test
    fun `a card lost in the post can be blocked before activation`() {
        assertEquals(CardState.BLOCKED, CardStateMachine.block(CardState.ISSUED))
    }

    @Test
    fun `only a customer freeze can be lifted`() {
        assertEquals(CardState.ACTIVE, CardStateMachine.unblock(CardState.BLOCKED, BlockReason.CUSTOMER_REQUEST))
        assertThrows<IllegalCardTransition> { CardStateMachine.unblock(CardState.BLOCKED, BlockReason.STOLEN) }
    }

    @Test
    fun `a replaced card is final`() {
        assertThrows<IllegalCardTransition> { CardStateMachine.block(CardState.REPLACED) }
        assertThrows<IllegalCardTransition> { CardStateMachine.activate(CardState.REPLACED) }
    }
}
