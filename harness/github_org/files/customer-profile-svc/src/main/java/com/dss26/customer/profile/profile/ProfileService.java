package com.dss26.customer.profile.profile;

import com.dss26.customer.profile.events.CustomerEvents;
import org.springframework.jdbc.core.DataClassRowMapper;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.NoSuchElementException;
import java.util.Optional;

@Service
public class ProfileService {

    private final NamedParameterJdbcTemplate jdbc;
    private final CustomerEvents events;

    public ProfileService(NamedParameterJdbcTemplate jdbc, CustomerEvents events) {
        this.jdbc = jdbc;
        this.events = events;
    }

    public Optional<Profile> find(String customerId) {
        return jdbc.query("SELECT * FROM customer_profile WHERE customer_id = :id",
                        new MapSqlParameterSource("id", customerId), new DataClassRowMapper<>(Profile.class))
                .stream().findFirst();
    }

    @Transactional
    public Profile update(Profile after, String changedBy, String agentId) {
        Profile before = find(after.customerId()).orElseThrow(() -> new NoSuchElementException(after.customerId()));
        List<String> changed = ChangedFields.between(before, after);
        if (changed.isEmpty()) {
            return before;
        }
        jdbc.update("""
                UPDATE customer_profile
                   SET first_name = :firstName, last_name = :lastName, date_of_birth = :dateOfBirth,
                       nationality = :nationality, email = :email, phone = :phone, address = :address,
                       marketing_email = :marketingEmail, marketing_sms = :marketingSms, updated_at = now()
                 WHERE customer_id = :customerId
                """, new MapSqlParameterSource()
                .addValue("customerId", after.customerId())
                .addValue("firstName", after.firstName())
                .addValue("lastName", after.lastName())
                .addValue("dateOfBirth", after.dateOfBirth())
                .addValue("nationality", after.nationality())
                .addValue("email", after.email())
                .addValue("phone", after.phone())
                .addValue("address", after.address())
                .addValue("marketingEmail", after.marketingEmail())
                .addValue("marketingSms", after.marketingSms()));
        events.profileUpdated(after.customerId(), changed, changedBy, agentId);
        return after;
    }
}
