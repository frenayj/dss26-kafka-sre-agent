package com.dss26.customer.profile.profile;

import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.function.Function;

/**
 * Which fields an update actually changed, as the snake_case names published
 * in customer.profile.updated.v1 (consumers such as sanctions screening decide
 * from these names whether to act).
 */
public final class ChangedFields {

    private record Field(String name, Function<Profile, Object> getter) {
    }

    private static final List<Field> FIELDS = List.of(
            new Field("first_name", Profile::firstName),
            new Field("last_name", Profile::lastName),
            new Field("date_of_birth", Profile::dateOfBirth),
            new Field("nationality", Profile::nationality),
            new Field("email", Profile::email),
            new Field("phone", Profile::phone),
            new Field("address", Profile::address),
            new Field("marketing_email", Profile::marketingEmail),
            new Field("marketing_sms", Profile::marketingSms));

    private ChangedFields() {
    }

    public static List<String> between(Profile before, Profile after) {
        List<String> changed = new ArrayList<>();
        for (Field f : FIELDS) {
            if (!Objects.equals(f.getter().apply(before), f.getter().apply(after))) {
                changed.add(f.name());
            }
        }
        return changed;
    }
}
