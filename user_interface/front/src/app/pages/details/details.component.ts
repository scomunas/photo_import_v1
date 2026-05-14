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
  totalFiles: number = 0;
  pendingTotal: number = 0;
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
    const filters = {
      filename: this.showFilters ? this.filterFileName : '',
      source_path: this.showFilters ? this.filterSourcePath : '',
      action: this.showFilters ? this.filterAction : '',
      status: this.showFilters ? this.filterStatus : ''
    };
    const offset = (this.currentPage - 1) * this.pageSize;
    
    this.fileService.getFiles(this.pageSize, offset, filters).subscribe(res => {
      this.files = res.data;
      this.totalFiles = res.total;
      this.pendingTotal = res.pending_total;
    });
  }

  /** Ficheros que aún se pueden procesar respetando los filtros actuales (obtenido del backend) */
  get pendingCount(): number {
    return this.pendingTotal;
  }

  onFilterChange() {
    this.currentPage = 1;
    this.loadFiles();
  }

  toggleFilters() {
    this.showFilters = !this.showFilters;
    if (!this.showFilters) {
      this.filterFileName = '';
      this.filterSourcePath = '';
      this.filterAction = '';
      this.filterStatus = '';
    }
    this.currentPage = 1;
    this.loadFiles();
  }

  // ── Paginación ────────────────────────────────────────────────────────────

  get totalPages(): number {
    return Math.ceil(this.totalFiles / this.pageSize) || 1;
  }

  get currentRangeEnd(): number {
    return Math.min(this.currentPage * this.pageSize, this.totalFiles);
  }

  nextPage() {
    if (this.currentPage < this.totalPages) {
      this.currentPage++;
      this.loadFiles();
    }
  }

  prevPage() {
    if (this.currentPage > 1) {
      this.currentPage--;
      this.loadFiles();
    }
  }

  onPageSizeChange() {
    this.currentPage = 1;
    this.loadFiles();
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
    if (this.pendingTotal === 0 || this.isProcessingAll) return;

    this.isProcessingAll = true;
    this.processAllProgress = 0;
    this.processAllTotal = this.pendingTotal;
    this.processErrorMap = {};

    const filters = {
      filename: this.showFilters ? this.filterFileName : '',
      source_path: this.showFilters ? this.filterSourcePath : '',
      action: this.showFilters ? this.filterAction : '',
      status: this.showFilters ? this.filterStatus : ''
    };

    this.fileService.processAllFiles(filters).subscribe({
      next: () => {
        // Since it runs in background, we just inform the user and maybe start a refresh interval
        // For now, we'll just stop the "loading" state and let the user refresh manually or wait
        // But a simple way is to reload files after a bit
        setTimeout(() => {
          this.isProcessingAll = false;
          this.loadFiles();
        }, 2000);
      },
      error: (err) => {
        this.isProcessingAll = false;
        console.error('Error starting process all', err);
      }
    });
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
