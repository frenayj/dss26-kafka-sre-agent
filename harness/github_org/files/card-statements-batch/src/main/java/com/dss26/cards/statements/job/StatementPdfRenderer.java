package com.dss26.cards.statements.job;

import com.dss26.cards.statements.job.Model.CardStatement;
import com.dss26.cards.statements.job.Model.StatementLine;
import com.lowagie.text.Document;
import com.lowagie.text.Font;
import com.lowagie.text.FontFactory;
import com.lowagie.text.PageSize;
import com.lowagie.text.Paragraph;
import com.lowagie.text.pdf.PdfPTable;
import com.lowagie.text.pdf.PdfWriter;
import org.springframework.stereotype.Component;

import java.io.ByteArrayOutputStream;
import java.time.ZoneId;
import java.time.format.DateTimeFormatter;

/** A4 PDF in the statement layout approved by Marketing and Compliance (template v4). */
@Component
public class StatementPdfRenderer {

    private static final DateTimeFormatter DAY = DateTimeFormatter.ofPattern("dd/MM/yyyy").withZone(ZoneId.of("Europe/Paris"));

    public byte[] render(CardStatement statement) {
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        Document doc = new Document(PageSize.A4, 48, 48, 56, 56);
        PdfWriter.getInstance(doc, out);
        doc.open();
        Font title = FontFactory.getFont(FontFactory.HELVETICA_BOLD, 14);
        doc.add(new Paragraph("DSS26 Bank - Card statement " + statement.cycle().period(), title));
        doc.add(new Paragraph("Card ending " + last4(statement.cycle().cardToken())));
        doc.add(new Paragraph("Opening balance: " + statement.cycle().openingBalance() + " " + statement.cycle().currency()));

        PdfPTable table = new PdfPTable(new float[]{2, 5, 2, 2});
        table.setWidthPercentage(100);
        table.addCell("Date");
        table.addCell("Merchant");
        table.addCell("Status");
        table.addCell("Amount");
        for (StatementLine line : statement.lines()) {
            table.addCell(DAY.format(line.authorisedAt()));
            table.addCell(line.merchantId());
            table.addCell(line.status());
            table.addCell(line.amount().toPlainString());
        }
        doc.add(table);
        doc.add(new Paragraph("Closing balance: " + statement.closingBalance() + " " + statement.cycle().currency(), title));
        doc.close();
        return out.toByteArray();
    }

    /** Tokens are not PANs; the token service exposes the last four digits as the token's suffix. */
    private static String last4(String cardToken) {
        return cardToken.length() > 4 ? cardToken.substring(cardToken.length() - 4) : cardToken;
    }
}
