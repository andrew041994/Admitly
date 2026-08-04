export type DateTimeField = {
  date: Date | null;
  time: Date | null;
};

export function applyDateSelection(field: DateTimeField, selectedDate: Date): DateTimeField {
  return {
    date: new Date(selectedDate.getTime()),
    time: field.time,
  };
}

export function applyTimeSelection(field: DateTimeField, selectedTime: Date): DateTimeField {
  return {
    date: field.date,
    time: new Date(selectedTime.getTime()),
  };
}

export function getConfirmedPickerValue(eventType: string, value?: Date): Date | null {
  if (eventType !== 'set' || !value || Number.isNaN(value.getTime())) {
    return null;
  }
  return value;
}

export function combineLocalDateAndTime(field: DateTimeField): Date | null {
  if (!field.date || !field.time) {
    return null;
  }

  return new Date(
    field.date.getFullYear(),
    field.date.getMonth(),
    field.date.getDate(),
    field.time.getHours(),
    field.time.getMinutes(),
    0,
    0,
  );
}

export function isEndAfterStart(startAt: DateTimeField, endAt: DateTimeField): boolean {
  const start = combineLocalDateAndTime(startAt);
  const end = combineLocalDateAndTime(endAt);
  return Boolean(start && end && end.getTime() > start.getTime());
}
