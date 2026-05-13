import { Component, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { FileService, ProcessedFile } from '../../services/file.service';
import { ConfigService, ImportConfig } from '../../services/config.service';
import { concatMap, from, tap, finalize, catchError, of } from 'rxjs';

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

  // Configuraciones para el filtro
  configs: ImportConfig[] = [];

  // Paginación
  currentPage = 1;
  pageSize = 50;
  pageSizeOptions = [50, 100, 200];

  // Filtros
  showFilters: boolean = false;
  filterFileName: string = '';
  filterSourcePath: string = '';
  filterAction: string = '';
  filterStatus: string = '';

  constructor(
    private fileService: FileService,
    private configService: ConfigService
  ) {}

  ngOnInit() {
    this.loadFiles();
    this.loadConfigs();
  }

  loadConfigs() {
    this.configService.getConfigs().subscribe(res => {
      this.configs = res;
    });
  }

  loadFiles() {
    this.fileService.getFiles().subscribe(res => {
      this.files = res;
    });
  }

  get filteredFiles(): ProcessedFile[] {
    if (!this.showFilters) {
      return this.files;
    }
    
    return this.files.filter(file => {
      const matchName = !this.filterFileName || (file.original_filename && file.original_filename.toLowerCase().includes(this.filterFileName.toLowerCase()));
      const matchPath = !this.filterSourcePath || (file.original_path && file.original_path.toLowerCase().includes(this.filterSourcePath.toLowerCase()));
      const matchAction = !this.filterAction || file.action === this.filterAction;
      const matchStatus = !this.filterStatus || file.status === this.filterStatus;
      return matchName && matchPath && matchAction && matchStatus;
    });
  }

  /** Ficheros que aún se pueden procesar respetando los filtros actuales */
  get actionableFiles(): ProcessedFile[] {
    return this.filteredFiles.filter(f => f.status === 'pending' || f.status === 'error');
  }

  get pendingCount(): number {
    return this.actionableFiles.length;
  }

  onFilterChange() {
    this.currentPage = 1;
  }

  toggleFilters() {
    this.showFilters = !this.showFilters;
    this.currentPage = 1;
  }

  // ── Paginación ────────────────────────────────────────────────────────────

  get totalPages(): number {
    return Math.ceil(this.filteredFiles.length / this.pageSize) || 1;
  }

  get paginatedFiles(): ProcessedFile[] {
    const startIndex = (this.currentPage - 1) * this.pageSize;
    return this.filteredFiles.slice(startIndex, startIndex + this.pageSize);
  }

  get currentRangeEnd(): number {
    return Math.min(this.currentPage * this.pageSize, this.filteredFiles.length);
  }

  nextPage() {
    if (this.currentPage < this.totalPages) {
      this.currentPage++;
    }
  }

  prevPage() {
    if (this.currentPage > 1) {
      this.currentPage--;
    }
  }

  onPageSizeChange() {
    this.currentPage = 1;
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
          tap(() => {
            this.processAllProgress++;
          }),
          catchError((err) => {
            this.processAllProgress++;
            const msg = err.error?.detail || 'Error connecting to NAS';
            this.processErrorMap[file.id] = msg;
            return of(null); // Prevents the outer stream from failing and stopping
          })
        )
      ),
      finalize(() => {
        this.isProcessingAll = false;
        this.loadFiles();
      })
    ).subscribe();
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
