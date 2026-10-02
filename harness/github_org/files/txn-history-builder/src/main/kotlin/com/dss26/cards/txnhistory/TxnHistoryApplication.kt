package com.dss26.cards.txnhistory

import org.springframework.boot.autoconfigure.SpringBootApplication
import org.springframework.boot.context.properties.ConfigurationPropertiesScan
import org.springframework.boot.runApplication

@SpringBootApplication
@ConfigurationPropertiesScan
class TxnHistoryApplication

fun main(args: Array<String>) {
    runApplication<TxnHistoryApplication>(*args)
}
