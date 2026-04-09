declare module '@react-native-community/datetimepicker' {
  import type { ComponentType } from 'react';

  export type DateTimePickerEvent = {
    type: 'set' | 'dismissed' | 'neutralButtonPressed';
  };

  export type DateTimePickerMode = 'date' | 'time' | 'datetime';

  export type DateTimePickerProps = {
    value: Date;
    mode: DateTimePickerMode;
    onChange: (event: DateTimePickerEvent, date?: Date) => void;
    is24Hour?: boolean;
  };

  const DateTimePicker: ComponentType<DateTimePickerProps>;

  export const DateTimePickerAndroid: {
    open: (params: DateTimePickerProps) => void;
  };

  export default DateTimePicker;
}
