package com.dss26.customer.profile.profile;

import java.time.LocalDate;

/** The contact-data master record for one customer. */
public record Profile(
        String customerId,
        String firstName,
        String lastName,
        LocalDate dateOfBirth,
        String nationality,
        String email,
        String phone,
        String address,
        boolean marketingEmail,
        boolean marketingSms) {
}
