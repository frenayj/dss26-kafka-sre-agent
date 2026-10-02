package com.dss26.payments.hub.iso20022;

import com.prowidesoftware.swift.model.mx.MxPacs00800108;
import com.prowidesoftware.swift.model.mx.dic.AccountIdentification4Choice;
import com.prowidesoftware.swift.model.mx.dic.ActiveCurrencyAndAmount;
import com.prowidesoftware.swift.model.mx.dic.BranchAndFinancialInstitutionIdentification6;
import com.prowidesoftware.swift.model.mx.dic.CashAccount38;
import com.prowidesoftware.swift.model.mx.dic.ChargeBearerType1Code;
import com.prowidesoftware.swift.model.mx.dic.CreditTransferTransaction39;
import com.prowidesoftware.swift.model.mx.dic.FIToFICustomerCreditTransferV08;
import com.prowidesoftware.swift.model.mx.dic.FinancialInstitutionIdentification18;
import com.prowidesoftware.swift.model.mx.dic.GroupHeader93;
import com.prowidesoftware.swift.model.mx.dic.PartyIdentification135;
import com.prowidesoftware.swift.model.mx.dic.PaymentIdentification7;
import com.prowidesoftware.swift.model.mx.dic.SettlementInstruction7;
import com.prowidesoftware.swift.model.mx.dic.SettlementMethod1Code;
import com.dss26.payments.hub.api.PaymentRequest;
import com.dss26.payments.hub.routing.Scheme;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.OffsetDateTime;

/**
 * Builds the interbank pacs.008 (FI to FI customer credit transfer) for SEPA,
 * T2 and SWIFT CBPR+. Scheme-specific usage rules (SEPA character set, CBPR+
 * structured addresses) are enforced before this point, in PaymentController.
 */
public final class Pacs008Builder {

    static final String OUR_BIC = "DSSBFRPPXXX";

    private Pacs008Builder() {
    }

    public static MxPacs00800108 build(PaymentRequest req, Scheme scheme, String endToEndId, String txId,
                                       String uetr, LocalDate settlementDate) {
        GroupHeader93 header = new GroupHeader93()
                .setMsgId(txId)
                .setCreDtTm(OffsetDateTime.now())
                .setNbOfTxs("1")
                .setSttlmInf(new SettlementInstruction7().setSttlmMtd(
                        scheme == Scheme.SWIFT_CBPR ? SettlementMethod1Code.INDA : SettlementMethod1Code.CLRG));

        CreditTransferTransaction39 tx = new CreditTransferTransaction39()
                .setPmtId(new PaymentIdentification7().setEndToEndId(endToEndId).setTxId(txId).setUETR(uetr))
                .setIntrBkSttlmAmt(new ActiveCurrencyAndAmount().setCcy(req.getCurrency())
                        .setValue(req.getAmount().setScale(2, java.math.RoundingMode.UNNECESSARY)))
                .setIntrBkSttlmDt(settlementDate)
                .setChrgBr(scheme == Scheme.SWIFT_CBPR ? ChargeBearerType1Code.SHAR : ChargeBearerType1Code.SLEV)
                .setDbtr(new PartyIdentification135().setNm(req.getDebtorName()))
                .setDbtrAcct(new CashAccount38().setId(new AccountIdentification4Choice().setIBAN(req.getDebtorIban())))
                .setDbtrAgt(institution(OUR_BIC))
                .setCdtrAgt(institution(req.getCreditorBic()))
                .setCdtr(new PartyIdentification135().setNm(req.getCreditorName()))
                .setCdtrAcct(new CashAccount38().setId(new AccountIdentification4Choice().setIBAN(req.getCreditorIban())));

        MxPacs00800108 mx = new MxPacs00800108();
        mx.setFIToFICstmrCdtTrf(new FIToFICustomerCreditTransferV08().setGrpHdr(header).addCdtTrfTxInf(tx));
        return mx;
    }

    private static BranchAndFinancialInstitutionIdentification6 institution(String bic) {
        return new BranchAndFinancialInstitutionIdentification6()
                .setFinInstnId(new FinancialInstitutionIdentification18().setBICFI(bic));
    }

    static boolean isWholeCents(BigDecimal amount) {
        return amount.stripTrailingZeros().scale() <= 2;
    }
}
