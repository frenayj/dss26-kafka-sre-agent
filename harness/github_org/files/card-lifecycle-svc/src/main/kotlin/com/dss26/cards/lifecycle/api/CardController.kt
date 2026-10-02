package com.dss26.cards.lifecycle.api

import com.dss26.cards.events.ActivationChannel
import com.dss26.cards.events.BlockInitiator
import com.dss26.cards.events.BlockReason
import com.dss26.cards.events.CardFormFactor
import com.dss26.cards.events.ReplacementReason
import com.dss26.cards.lifecycle.card.Card
import com.dss26.cards.lifecycle.card.CardService
import jakarta.validation.Valid
import jakarta.validation.constraints.NotBlank
import jakarta.validation.constraints.Pattern
import org.springframework.http.ResponseEntity
import org.springframework.web.bind.annotation.GetMapping
import org.springframework.web.bind.annotation.PathVariable
import org.springframework.web.bind.annotation.PostMapping
import org.springframework.web.bind.annotation.RequestBody
import org.springframework.web.bind.annotation.RequestMapping
import org.springframework.web.bind.annotation.RestController

@RestController
@RequestMapping("/v1/cards")
class CardController(private val cards: CardService) {

    data class IssueRequest(
        @field:NotBlank val cardToken: String,
        @field:NotBlank val customerId: String,
        @field:NotBlank val productCode: String,
        val formFactor: CardFormFactor,
        @field:Pattern(regexp = "\\d{6}") val bin: String,
        @field:Pattern(regexp = "\\d{6}") val expiryYyyymm: String,
    )

    data class BlockRequest(val reason: BlockReason, val initiator: BlockInitiator = BlockInitiator.CUSTOMER)
    data class ActivateRequest(val channel: ActivationChannel)
    data class ReplaceRequest(@field:NotBlank val newCardToken: String, val reason: ReplacementReason,
                              @field:Pattern(regexp = "\\d{6}") val expiryYyyymm: String)

    @GetMapping("/{cardToken}")
    fun get(@PathVariable cardToken: String): ResponseEntity<Card> =
        cards.find(cardToken)?.let { ResponseEntity.ok(it) } ?: ResponseEntity.notFound().build()

    @PostMapping
    fun issue(@Valid @RequestBody req: IssueRequest): Card =
        cards.issue(req.cardToken, req.customerId, req.productCode, req.formFactor, req.bin, req.expiryYyyymm)

    @PostMapping("/{cardToken}/activation")
    fun activate(@PathVariable cardToken: String, @RequestBody req: ActivateRequest): Card =
        cards.activate(cardToken, req.channel)

    @PostMapping("/{cardToken}/block")
    fun block(@PathVariable cardToken: String, @RequestBody req: BlockRequest): Card =
        cards.block(cardToken, req.reason, req.initiator)

    @PostMapping("/{cardToken}/replacement")
    fun replace(@PathVariable cardToken: String, @Valid @RequestBody req: ReplaceRequest): Card =
        cards.replace(cardToken, req.newCardToken, req.reason, req.expiryYyyymm)
}
