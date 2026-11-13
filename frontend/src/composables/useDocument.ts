import { ref } from "vue";
import { getDocumentPages, uploadPdf } from "../services/api";
import type { DocumentDetails, UploadResult } from "../types/document";

export function useDocument() {
  const document = ref<DocumentDetails | null>(null);
  const selectedPage = ref<number | null>(null);
  const uploading = ref(false);
  const loadingDocument = ref(false);
  const uploadError = ref("");
  const documentError = ref("");
  const uploadSuccess = ref("");
  let selectionVersion = 0;

  async function selectDocument(fileId: number, pageNumber?: number): Promise<void> {
    const version = ++selectionVersion;
    document.value = null;
    selectedPage.value = null;
    documentError.value = "";
    loadingDocument.value = true;
    try {
      const savedDocument = await getDocumentPages(fileId);
      // Rapidly selecting another file must not show an older request's result.
      if (version === selectionVersion) {
        document.value = savedDocument;
        if (pageNumber !== undefined) {
          if (savedDocument.pages.some(page => page.page_number === pageNumber)) {
            selectedPage.value = pageNumber;
          } else {
            documentError.value = "The requested page could not be found. Open the file from Saved files to view available pages.";
          }
        }
      }
    } catch (error) {
      if (version === selectionVersion) {
        documentError.value = error instanceof Error ? error.message : "Could not load saved results.";
      }
    } finally {
      if (version === selectionVersion) loadingDocument.value = false;
    }
  }

  async function uploadDocument(file: File): Promise<UploadResult | null> {
    if (uploading.value) return null;
    uploading.value = true;
    uploadError.value = "";
    uploadSuccess.value = "";
    try {
      const result = await uploadPdf(file);
      uploadSuccess.value = `Uploaded and extracted ${result.filename} (${result.page_count} pages).`;
      return result;
    } catch (error) {
      uploadError.value = error instanceof Error ? error.message : "Could not upload the PDF.";
      return null;
    } finally {
      uploading.value = false;
    }
  }

  function clearDocument(): void {
    // Invalidate pending reads when history navigation removes the file selection.
    selectionVersion += 1;
    document.value = null;
    selectedPage.value = null;
    documentError.value = "";
    loadingDocument.value = false;
  }

  return {
    document, selectedPage, uploading, loadingDocument, uploadError, documentError,
    uploadSuccess, uploadDocument, selectDocument, clearDocument,
  };
}
