package com.bonddesk.oms.event;

import com.bonddesk.contracts.EventType;
import com.bonddesk.contracts.OrderEventRecord;
import com.bonddesk.contracts.OrderStatus;
import org.apache.avro.Schema;
import org.apache.avro.SchemaCompatibility;
import org.apache.avro.SchemaCompatibility.SchemaCompatibilityType;
import org.apache.avro.generic.GenericDatumReader;
import org.apache.avro.generic.GenericRecord;
import org.apache.avro.io.DatumWriter;
import org.apache.avro.io.Decoder;
import org.apache.avro.io.DecoderFactory;
import org.apache.avro.io.Encoder;
import org.apache.avro.io.EncoderFactory;
import org.apache.avro.specific.SpecificData;
import org.apache.avro.specific.SpecificDatumWriter;
import org.junit.jupiter.api.Test;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.math.BigDecimal;
import java.time.Instant;

import static org.assertj.core.api.Assertions.assertThat;

/**
 * The schema-management guarantees the Schema Registry gives us, checked mechanically in CI without any
 * broker or registry: a BACKWARD-compatible evolution is accepted, a breaking one is rejected, and data
 * written with the old schema is still readable by a consumer on the new one. This is the test that
 * fails the build before an incompatible schema change can reach the topic and mis-aggregate risk.
 */
class OrderEventSchemaCompatibilityTest {

    /** The live, deployed schema — exactly what the generated producer/consumer types encode. */
    private final Schema v1 = OrderEventRecord.getClassSchema();

    @Test
    void addingAnOptionalFieldWithADefaultIsBackwardCompatible() throws Exception {
        Schema v2 = load("/schema/order-event-v2.avsc");
        // BACKWARD = a consumer on the NEW schema (reader) can read data written with the OLD one (writer).
        SchemaCompatibility.SchemaPairCompatibility result =
                SchemaCompatibility.checkReaderWriterCompatibility(v2, v1);
        assertThat(result.getType()).isEqualTo(SchemaCompatibilityType.COMPATIBLE);
    }

    @Test
    void addingARequiredFieldWithoutADefaultIsRejected() throws Exception {
        Schema v3 = load("/schema/order-event-v3-incompatible.avsc");
        SchemaCompatibility.SchemaPairCompatibility result =
                SchemaCompatibility.checkReaderWriterCompatibility(v3, v1);
        assertThat(result.getType()).isEqualTo(SchemaCompatibilityType.INCOMPATIBLE);
    }

    @Test
    void dataWrittenWithV1IsReadableByAV2Consumer() throws Exception {
        Schema v2 = load("/schema/order-event-v2.avsc");
        byte[] writtenWithV1 = writeV1();

        // Resolve v1-written bytes against the v2 reader schema — the new 'venue' field takes its default.
        GenericDatumReader<GenericRecord> reader = new GenericDatumReader<>(v1, v2);
        Decoder decoder = DecoderFactory.get().binaryDecoder(writtenWithV1, null);
        GenericRecord out = reader.read(null, decoder);

        assertThat(out.get("orderRef").toString()).isEqualTo("O-1");
        assertThat(out.get("venue")).isNull();
    }

    private static Schema load(String resource) throws Exception {
        try (InputStream in = OrderEventSchemaCompatibilityTest.class.getResourceAsStream(resource)) {
            return new Schema.Parser().parse(in);
        }
    }

    private byte[] writeV1() throws Exception {
        OrderEventRecord record = OrderEventRecord.newBuilder()
                .setType(EventType.ORDER_FILLED)
                .setOrderRef("O-1")
                .setCusip("912828XG8")
                .setPortfolio("DESK-A")
                .setStatus(OrderStatus.FILLED)
                .setQuantity(new BigDecimal("1000000.00"))
                .setFilledQuantity(new BigDecimal("1000000.00"))
                .setOccurredAt(Instant.parse("2026-01-01T00:00:00Z"))
                .build();
        // Use the generated type's own model so the decimal/timestamp logical-type conversions apply.
        SpecificData model = SpecificData.getForClass(OrderEventRecord.class);
        DatumWriter<OrderEventRecord> writer = new SpecificDatumWriter<>(v1, model);
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        Encoder encoder = EncoderFactory.get().binaryEncoder(out, null);
        writer.write(record, encoder);
        encoder.flush();
        return out.toByteArray();
    }
}
