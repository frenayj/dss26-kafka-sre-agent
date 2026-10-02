package com.dss26.customer.profile.api;

import com.dss26.customer.events.ConsentType;
import com.dss26.customer.profile.consent.ConsentService;
import com.dss26.customer.profile.gdpr.ErasureService;
import com.dss26.customer.profile.profile.Profile;
import com.dss26.customer.profile.profile.ProfileService;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.Map;

@RestController
@RequestMapping("/v1/customers")
public class ProfileController {

    public record ConsentRequest(ConsentType type, String scope) {
    }

    private final ProfileService profiles;
    private final ConsentService consents;
    private final ErasureService erasure;

    public ProfileController(ProfileService profiles, ConsentService consents, ErasureService erasure) {
        this.profiles = profiles;
        this.consents = consents;
        this.erasure = erasure;
    }

    @GetMapping("/{customerId}")
    public ResponseEntity<Profile> get(@PathVariable String customerId) {
        return ResponseEntity.of(profiles.find(customerId));
    }

    /** Channels send X-Changed-By: CUSTOMER; the contact-centre desktop sends its operator id too. */
    @PutMapping("/{customerId}")
    public Profile update(@PathVariable String customerId, @RequestBody Profile profile,
                          @RequestHeader(value = "X-Changed-By", defaultValue = "CUSTOMER") String changedBy,
                          @RequestHeader(value = "X-Operator-Id", required = false) String operatorId) {
        return profiles.update(profile, changedBy, operatorId);
    }

    @PostMapping("/{customerId}/consents")
    public Map<String, String> grant(@PathVariable String customerId, @RequestBody ConsentRequest req) {
        return Map.of("consentId", consents.grant(customerId, req.type(), req.scope()));
    }

    @DeleteMapping("/{customerId}")
    public ResponseEntity<Void> erase(@PathVariable String customerId) {
        return erasure.erase(customerId) ? ResponseEntity.noContent().build() : ResponseEntity.status(409).build();
    }
}
