import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { ConfigService, ImportConfig } from '../../services/config.service';

@Component({
  selector: 'app-settings',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './settings.component.html',
  styleUrl: './settings.component.css'
})
export class SettingsComponent implements OnInit, OnDestroy {
  configs: ImportConfig[] = [];
  pollingInterval: any;
  editingId: number | null = null;
  isAdding = false;
  isScanningAll = false;
  tempConfig: any = null;

  expandedRows: Set<number> = new Set();
  scansData: { [key: number]: any[] } = {};
  isRefreshingScan: { [key: number]: boolean } = {};

  constructor(private configService: ConfigService) {}

  ngOnInit() {
    this.loadConfigs();
  }

  ngOnDestroy() {
    this.stopPolling();
  }

  loadConfigs() {
    this.configService.getConfigs().subscribe(res => {
      this.configs = res;
      
      const isAnyImporting = this.configs.some(c => c.import_status === 'importing');
      if (isAnyImporting) {
        this.startPolling();
      } else {
        this.stopPolling();
      }
    });
  }

  startPolling() {
    if (!this.pollingInterval) {
      this.pollingInterval = setInterval(() => {
        this.loadConfigs();
      }, 3000);
    }
  }

  stopPolling() {
    if (this.pollingInterval) {
      clearInterval(this.pollingInterval);
      this.pollingInterval = null;
    }
  }

  startAdd() {
    this.isAdding = true;
    this.editingId = null;
    this.tempConfig = {
      source_path: '',
      target_path: '',
      path_template: '{year}/{month}',
      name_template: '{filename}',
      action: 'move'
    };
  }

  startEdit(config: ImportConfig) {
    this.isAdding = false;
    this.editingId = config.id;
    this.tempConfig = { ...config };
  }

  cancelEdit() {
    this.editingId = null;
    this.isAdding = false;
    this.tempConfig = null;
  }

  saveEdit() {
    if (this.tempConfig) {
      if (this.isAdding) {
        this.configService.addConfig(this.tempConfig).subscribe(() => {
          this.loadConfigs();
          this.cancelEdit();
        });
      } else if (this.editingId) {
        this.configService.updateConfig(this.editingId, this.tempConfig).subscribe(() => {
          this.loadConfigs();
          this.cancelEdit();
        });
      }
    }
  }

  toggleRow(configId: number) {
    if (this.expandedRows.has(configId)) {
      this.expandedRows.delete(configId);
    } else {
      this.expandedRows.add(configId);
      this.loadScans(configId);
    }
  }

  isExpanded(configId: number): boolean {
    return this.expandedRows.has(configId);
  }

  loadScans(configId: number) {
    this.isRefreshingScan[configId] = true;
    this.configService.getScans(configId).subscribe(
      scans => {
        this.scansData[configId] = scans;
        this.isRefreshingScan[configId] = false;
      },
      error => {
        console.error('Error loading scans', error);
        this.isRefreshingScan[configId] = false;
      }
    );
  }

  onScanClick(configId: number, event: Event) {
    event.stopPropagation(); // prevent row toggle if clicked on button
    this.configService.triggerScan(configId).subscribe({
      next: () => {
        if (!this.expandedRows.has(configId)) {
          this.expandedRows.add(configId);
        }
        this.loadScans(configId);
      },
      error: err => console.error('Error triggering scan', err)
    });
  }

  scanAll() {
    if (this.configs.length === 0) return;
    this.isScanningAll = true;
    let completed = 0;
    
    this.configs.forEach(config => {
      this.configService.triggerScan(config.id).subscribe({
        next: () => {
          if (!this.expandedRows.has(config.id)) {
            this.expandedRows.add(config.id);
          }
          this.loadScans(config.id);
        },
        error: err => {
          console.error(`Error triggering scan for config ${config.id}`, err);
          completed++;
          if (completed === this.configs.length) this.isScanningAll = false;
        },
        complete: () => {
          completed++;
          if (completed === this.configs.length) this.isScanningAll = false;
        }
      });
    });
  }

  onImportClick(configId: number, event: Event) {
    event.stopPropagation();
    const config = this.configs.find(c => c.id === configId);
    if (config) {
      config.import_status = 'importing';
    }
    this.startPolling();
    
    this.configService.triggerImport(configId).subscribe(
      () => {},
      error => {
        console.error('Error triggering import', error);
        this.loadConfigs();
      }
    );
  }
}
