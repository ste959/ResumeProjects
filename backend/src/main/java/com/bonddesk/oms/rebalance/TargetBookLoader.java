package com.bonddesk.oms.rebalance;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

/**
 * Reads the research target book from disk (path from {@code oms.rebalance.target-book-path})
 * and parses it into a {@link TargetBook} via the shared Jackson {@link ObjectMapper}.
 * Throws a clear exception if the file is missing or unparseable rather than silently
 * routing against an empty book.
 */
@Component
public class TargetBookLoader {

    private static final Logger log = LoggerFactory.getLogger(TargetBookLoader.class);

    private final ObjectMapper json;
    private final RebalanceProperties props;

    public TargetBookLoader(ObjectMapper json, RebalanceProperties props) {
        this.json = json;
        this.props = props;
    }

    /** Load the target book from the configured path. */
    public TargetBook load() {
        return load(props.getTargetBookPath());
    }

    /** Load the target book from an explicit path (used by tests). */
    public TargetBook load(String path) {
        Path file = Path.of(path);
        if (!Files.isRegularFile(file)) {
            throw new IllegalStateException("Target-book file not found at " + file.toAbsolutePath()
                    + " (configure oms.rebalance.target-book-path)");
        }
        try {
            TargetBook book = json.readValue(file.toFile(), TargetBook.class);
            if (book.names() == null || book.names().isEmpty()) {
                throw new IllegalStateException("Target book " + file + " has no names");
            }
            log.info("Loaded target book '{}' asOf {} with {} names from {}",
                    book.strategy(), book.asOf(), book.names().size(), file);
            return book;
        } catch (IOException e) {
            throw new IllegalStateException("Unable to parse target book at " + file + ": " + e.getMessage(), e);
        }
    }

    /** Parse a target book from a raw JSON string (used by tests). */
    public TargetBook parse(String jsonBody) {
        try {
            return json.readValue(jsonBody, TargetBook.class);
        } catch (IOException e) {
            throw new IllegalStateException("Unable to parse target book JSON: " + e.getMessage(), e);
        }
    }
}
