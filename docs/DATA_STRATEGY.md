# ReStore: data strategy and pitch evidence

## What the prototype delivers

Local PDF/PPTX/MP4 uploads become searchable text and cached slide or video images.
Video results preserve timestamps and associate each passage with its greatest-overlap
visual (ties choose the earlier image). Missing or unfinished visuals do not suppress
searchable speech. Search previews and deep links reuse this same association.

Savings compare the recorded original upload bytes with the exact downloadable
representation: HTML with timestamps off when images exist, otherwise UTF-8 text.
The streamed serializer counts markup, base64, repeated images and non-ASCII text.
The payload breakdown is raw text + unique JPEGs + the measured packaging adjustment;
it is not a second independent saving. Timestamped HTML can have a different size.
Use **Storage details → Download the measured file** to verify each scenario.
No assumed “1 GB to 2 MB” scenario is used as a measured result.

For each pitch scenario, show the source type/duration, original byte count, downloaded
byte count, export format and percentage. Open the downloaded document to demonstrate
what information remains. Include a static presentation, a screen demonstration,
and a recording with few useful visuals. A larger output is a negative saving.
Incomplete or unavailable output must not be presented as a successful reduction.

Originals remain retained: the report measures potential reduction, not reclaimed
storage. Text and sampled images do not preserve voice, motion, every screen detail,
or guaranteed transcription accuracy. Do not claim a lossless replacement or that
visual similarity proves equivalent information.

## Future cross-system indexing (not implemented)

1. Start with read-only SharePoint/OneDrive/Ericsson Play connectors. Record source
   system, immutable source ID/version, URI, owner and access rules. Keep source
   identifiers separate from filenames so renames and “(1)” suffixes do not break identity.
2. Stream hashes from actual accessible bytes. Index content by hash/size, with separate
   source-location records. Keep the distinction between identical file bytes,
   equivalent rendered slides and merely similar visuals.
3. Maintain a canonical slide registry with source document number, revision and page
   number. Match video frames against it as review candidates; retain time intervals
   and provenance even when the image is shared. Never treat a pHash collision as an
   exact content identity.
4. Publish versioned JSON/JSONL manifests referencing text, images, time ranges,
   extraction version, source version and permissions. These are inputs for AI systems;
   model training, a chatbot and a vector database are not prerequisites.
5. Propagate source permission and deletion changes into search and exports. Keep
   content local unless its owner explicitly approves an external destination.

## Future cleanup and employee departure workflow (not implemented)

Inventory the departing owner's accessible files; identify exact duplicate locations
and an approved keeper. Verify the keeper exists, its hash/version still matches,
and intended users retain access. Content similarity alone cannot authorize deletion.
Before replacing an original with a compact document, verify the export and explicitly
accept the information not preserved. Check retention obligations and legal holds.

Present a dry-run plan with the exact affected source IDs, keeper, evidence and byte
measurements. Require explicit approval, then use reversible source trash/versioning
where available. Log actor, source versions, exported-artifact hash and actual reclaimed
bytes. Revalidate immediately before each action; stop if the keeper changed or became
unavailable. Never follow a chain of recommendations that removes all copies.

## Acceptance gates for that future work

Cross-system duplicate records must respect access boundaries. Cleanup must refuse a
missing keeper, permission loss, changed bytes, a retention hold or an incomplete export.
Report actual reclaimed bytes separately from potential savings and from raw payload.
Validate transcript accuracy and visual coverage with representative Ericsson samples.
