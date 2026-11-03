import { describe, expect, it } from 'vitest';
import { toCardModel } from './presenters';
import {
  failedEntry,
  skippedEntry,
  soilEntryOk,
  spiEntryOk,
  tempEntryOkWithFallback,
  undefinedEntry,
} from '../test/fixtures';

describe('toCardModel', () => {
  it('maps a computed SPI entry to values, units, and provenance', () => {
    const model = toCardModel(spiEntryOk());
    expect(model.title).toContain('SPI');
    expect(model.status).toBe('ok');
    expect(model.headlines).toContainEqual({ label: 'SPI', value: '-0.517' });
    expect(model.headlines).toContainEqual({ label: 'Window total', value: '76.87 mm' });
    expect(model.reference).toContain('1991–2020');
    expect(model.reference).toContain('2024-03');
    expect(model.dataSource).toBe('CHIRPS v3.0');
    expect(model.coverage).toContain('60°S–60°N');
    expect(model.limitations).toHaveLength(1);
    expect(model.citation).toContain('Funk');
    expect(model.doi).toBe('10.1038/sdata.2015.66');
    expect(model.chart).not.toBeNull();
    expect(model.chart?.nYears).toBe(30);
  });

  it('flags the cell-edge point and the excluded reference year', () => {
    const model = toCardModel(spiEntryOk());
    expect(model.warnings.some((w) => w.includes('cell edge'))).toBe(true);
    expect(model.warnings.some((w) => w.includes('1993'))).toBe(true);
    expect(model.usedPoint).toContain('30.4');
    expect(model.usedPoint).toContain('-9.6');
  });

  it('reports the ERA5 land fallback prominently', () => {
    const model = toCardModel(tempEntryOkWithFallback());
    expect(model.headlines).toContainEqual({ label: 'Anomaly', value: '+2.22 °C' });
    expect(model.headlines).toContainEqual({
      label: 'Rank among reference years',
      value: '96.7th percentile of 30 years',
    });
    const fallback = model.warnings.find((w) => w.includes('Land fallback'));
    expect(fallback).toBeDefined();
    expect(fallback).toContain('30.50°');
    expect(fallback).toContain('15 km');
    expect(model.usedPoint).toBe('30.50°, -9.60°');
    expect(model.chart?.unit).toBe('°C');
    expect(model.chart?.percentilePct).toBeCloseTo(96.7, 1);
  });

  it('maps soil moisture with its layer and units', () => {
    const model = toCardModel(soilEntryOk());
    expect(model.headlines).toContainEqual({
      label: 'Anomaly',
      value: '-0.0505 m³/m³',
    });
    expect(model.headlines).toContainEqual({ label: 'Soil layer', value: '0–7 cm' });
    expect(model.chart?.unit).toBe('m³/m³');
  });

  it('exposes a method note for SPI and window-anomaly cards', () => {
    expect(toCardModel(spiEntryOk()).method).toContain('Gamma distribution');
    expect(toCardModel(tempEntryOkWithFallback()).method).toContain(
      'Day-weighted window mean',
    );
    expect(toCardModel(soilEntryOk()).method).toContain('Day-weighted window mean');
  });

  it('maps a failed entry to a typed error without values', () => {
    const model = toCardModel(failedEntry());
    expect(model.status).toBe('failed');
    expect(model.errorType).toBe('data_not_available');
    expect(model.errorMessage).toContain('No observations');
    expect(model.headlines).toEqual([]);
    expect(model.chart).toBeNull();
  });

  it('maps skipped and undefined entries to honest states', () => {
    const skipped = toCardModel(skippedEntry());
    expect(skipped.headlines).toEqual([]);
    expect(skipped.chart).toBeNull();
    expect(skipped.warnings).toEqual(['Not requested in this scenario.']);

    const undefinedModel = toCardModel(undefinedEntry());
    expect(undefinedModel.status).toBe('undefined');
    expect(undefinedModel.chart).toBeNull();
    expect(undefinedModel.warnings.some((w) => w.includes('Zero reference variance'))).toBe(
      true,
    );
  });

  it('never emits severity language', () => {
    const entries = [spiEntryOk(), tempEntryOkWithFallback(), soilEntryOk(), failedEntry()];
    const banned = /\bsevere\b|\bseverity\b|extreme drought|drought categor/i;
    for (const entry of entries) {
      const model = toCardModel(entry);
      const text = JSON.stringify(model);
      expect(text, entry.indicator).not.toMatch(banned);
    }
  });
});
