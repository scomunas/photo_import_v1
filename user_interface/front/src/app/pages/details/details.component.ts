import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { FileService, ProcessedFile } from '../../services/file.service';
import { concatMap, from, tap, finalize } from 'rxjs';

@Component({
  selector: 'app-details',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './details.component.html',
  styleUrl: './details.component.css'
})
export class DetailsComponent implements OnInit {
  files: ProcessedFile[] = [];
  editingFileId: number | null = null;
  editData: Partial<ProcessedFile> = {};

  // Estado por fichero (botón Process individual)
  processingIds = new Set<number>();
  processErrorMap: Record<number, string> = {};

  // Estado del Process All
  isProcessingAll = false;
  processAllProgress = 0;
  processAllTotal = 0;

  constructor(private fileService: FileService) {}

  ngOnInit() {
    this.loadFiles();
  }

  loadFiles() {
    this.fileService.getFiles().subscribe(res => {
      this.files = res;
    });
  }

  /** Ficheros que aún se pueden procesar */
  get actionableFiles(): ProcessedFile[] {
    return this.files.filter(f => f.status === 'pending' || f.status === 'error');
  }

  get pendingCount(): number {
    return this.actionableFiles.length;
  }

  // ── Process individual ────────────────────────────────────────────────────

  onImport(file: ProcessedFile) {
    if (this.processingIds.has(file.id)) return;

    this.processingIds.add(file.id);
    delete this.processErrorMap[file.id];

    this.fileService.processFile(file.id).subscribe({
      next: () => {
        this.processingIds.delete(file.id);
        this.loadFiles();
      },
      error: (err) => {
        this.processingIds.delete(file.id);
        const msg = err.error?.detail || 'Error connecting to NAS';
        this.processErrorMap[file.id] = msg;
        this.loadFiles();
      }
    });
  }

  isProcessing(fileId: number): boolean {
    return this.processingIds.has(fileId) || this.isProcessingAll;
  }

  getProcessError(fileId: number): string | null {
    return this.processErrorMap[fileId] || null;
  }

  // ── Process All ───────────────────────────────────────────────────────────

  processAll() {
    const targets = this.actionableFiles;
    if (!targets.length || this.isProcessingAll) return;

    this.isProcessingAll = true;
    this.processAllProgress = 0;
    this.processAllTotal = targets.length;
    this.processErrorMap = {};

    from(targets).pipe(
      concatMap(file =>
        this.fileService.processFile(file.id).pipe(
          tap({
            next: () => { this.processAllProgress++; },
            error: (err) => {
              this.processAllProgress++;
              const msg = err.error?.detail || 'Error connecting to NAS';
              this.processErrorMap[file.id] = msg;
            }
          })
        )
      ),
      finalize(() => {
        this.isProcessingAll = false;
        this.loadFiles();
      })
    ).subscribe({ error: () => {} }); // errores individuales ya capturados en tap
  }

  // ── Edit inline ───────────────────────────────────────────────────────────

  startEdit(file: ProcessedFile) {
    this.editingFileId = file.id;
    this.editData = {
      target_path: file.target_path,
      target_filename: file.target_filename,
      status: file.status,
      error_details: file.error_details
    };
  }

  saveEdit() {
    if (!this.editingFileId) return;
    this.fileService.updateFile(this.editingFileId, this.editData).subscribe({
      next: () => {
        this.editingFileId = null;
        this.loadFiles();
      },
      error: (err) => console.error('Error saving edit', err)
    });
  }

  cancelEdit() {
    this.editingFileId = null;
    this.editData = {};
  }

  // ── Helpers ───────────────────────────────────────────────────────────────

  formatDate(dateStr: string) {
    const date = new Date(dateStr);
    return date.toLocaleDateString('en-GB', {
      day: '2-digit',
      month: 'short',
      year: 'numeric'
    });
  }

  isImage(filename: string): boolean {
    const ext = filename?.split('.').pop()?.toLowerCase();
    return ['jpg', 'jpeg', 'png', 'heic'].includes(ext || '');
  }
}
