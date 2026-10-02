package com.dss26.core.adapter;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.jms.annotation.EnableJms;

@SpringBootApplication
@EnableJms
public class CoreBankingAdapterApplication {

    public static void main(String[] args) {
        SpringApplication.run(CoreBankingAdapterApplication.class, args);
    }
}
