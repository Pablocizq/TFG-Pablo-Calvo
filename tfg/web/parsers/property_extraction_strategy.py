from abc import ABC, abstractmethod
from typing import List, Dict, Any
import re
import csv
import json
from io import StringIO
from datetime import datetime


class PropertyInfo: 
    DATA_TYPE_TEXT = 'text'
    DATA_TYPE_NUMERIC = 'numeric'
    DATA_TYPE_DATE = 'date'
    DATA_TYPE_COORDINATES = 'coordinates'
    DATA_TYPE_BOOLEAN = 'boolean'
    
    def __init__(self, name: str, data_type: str):
        self.name = name
        self.data_type = data_type
    
    def to_dict(self) -> Dict[str, str]:
        return {
            'name': self.name,
            'type': self.data_type
        }


class PropertyExtractionStrategy(ABC):
   
    @abstractmethod
    def extract_properties(self, content: str) -> List[PropertyInfo]:
        pass
    
    def _detect_type(self, value: Any) -> str:
        if value is None or value == '':
            return PropertyInfo.DATA_TYPE_TEXT
        
        value_str = str(value).strip()
        
        if self._is_boolean(value_str):
            return PropertyInfo.DATA_TYPE_BOOLEAN
        
        if self._is_numeric(value_str):
            return PropertyInfo.DATA_TYPE_NUMERIC
        
        if self._is_coordinates(value_str):
            return PropertyInfo.DATA_TYPE_COORDINATES
        
        if self._is_date(value_str):
            return PropertyInfo.DATA_TYPE_DATE
        
        return PropertyInfo.DATA_TYPE_TEXT
    
    def _is_boolean(self, value: str) -> bool:
        value_lower = value.lower()
        return value_lower in ['true', 'false', 'yes', 'no', '0', '1', 'si', 'sí']
    
    def _is_numeric(self, value: str) -> bool:
        numeric_pattern = r'^-?\d+\.?\d*([eE][-+]?\d+)?$'
        return bool(re.match(numeric_pattern, value))
    
    def _is_coordinates(self, value: str) -> bool:
        latlong_pattern = r'^-?\d+\.?\d*\s*,\s*-?\d+\.?\d*$'
        if re.match(latlong_pattern, value):
            return True
        
        if 'point' in value.lower() and ('coordinates' in value.lower() or '[' in value):
            return True
        
        if any(keyword in value.upper() for keyword in ['POINT', 'POLYGON', 'LINESTRING']):
            return True
        
        return False
    
    def _is_date(self, value: str) -> bool:
        date_patterns = [
            r'^\d{4}-\d{2}-\d{2}',
            r'^\d{2}/\d{2}/\d{4}',
            r'^\d{4}/\d{2}/\d{2}',
            r'^\d{2}-\d{2}-\d{4}',
        ]
        
        for pattern in date_patterns:
            if re.match(pattern, value):
                return True
        
        date_formats = [
            '%Y-%m-%d',
            '%d/%m/%Y',
            '%m/%d/%Y',
            '%Y/%m/%d',
            '%d-%m-%Y',
            '%Y-%m-%dT%H:%M:%S',
            '%Y-%m-%d %H:%M:%S',
        ]
        
        for fmt in date_formats:
            try:
                datetime.strptime(value, fmt)
                return True
            except ValueError:
                continue
        
        return False


class CSVExtractionStrategy(PropertyExtractionStrategy):
    
    def extract_properties(self, content: str) -> List[PropertyInfo]:
        try:
            lines = content.split('\n')
            if len(lines) < 2:
                return []
            
            csv_reader = csv.reader(StringIO(content))
            headers = next(csv_reader)
            
            try:
                first_row = next(csv_reader)
            except StopIteration:
                return [PropertyInfo(h.strip(), PropertyInfo.DATA_TYPE_TEXT) for h in headers if h.strip()]
            
            properties = []
            for i, header in enumerate(headers):
                header = header.strip()
                if not header:
                    continue
                
                value = first_row[i] if i < len(first_row) else ''
                data_type = self._detect_type(value)
                properties.append(PropertyInfo(header, data_type))
            
            return properties
        except Exception as e:
            print(f"Error extracting CSV properties: {e}")
            return []


class JSONExtractionStrategy(PropertyExtractionStrategy):
    
    def extract_properties(self, content: str) -> List[PropertyInfo]:
        try:
            data = json.loads(content)
            
            if isinstance(data, list):
                if not data or not isinstance(data[0], dict):
                    return []
                data = data[0]
            
            if isinstance(data, dict):
                properties = []
                for key, value in data.items():
                    data_type = self._detect_type(value)
                    formatted_name = self._format_property_name(key)
                    properties.append(PropertyInfo(formatted_name, data_type))
                return properties
            
            return []
        except Exception as e:
            print(f"Error extracting JSON properties: {e}")
            return []
    
    def _format_property_name(self, name: str) -> str:
        if not name:
            return ''
        return name.replace('_', ' ').replace('-', ' ').strip()


class RDFXMLExtractionStrategy(PropertyExtractionStrategy):
    
    def extract_properties(self, content: str) -> List[PropertyInfo]:
        try:
            properties = {}
            
            predicate_pattern = r'<([a-zA-Z0-9_-]+):([a-zA-Z0-9_-]+)[^>]*>([^<]*)<'
            
            sample_content = content[:10000] if len(content) > 10000 else content
            
            for match in re.finditer(predicate_pattern, sample_content):
                namespace = match.group(1)
                predicate = match.group(2)
                value = match.group(3).strip()
                
                if namespace.lower() == 'rdf' and predicate in ['RDF', 'Description', 'Bag', 'Seq']:
                    continue
                
                prop_name = self._format_property_name(predicate)
                
                if value and prop_name not in properties:
                    data_type = self._detect_type(value)
                    properties[prop_name] = PropertyInfo(prop_name, data_type)
                elif prop_name not in properties:
                    properties[prop_name] = PropertyInfo(prop_name, PropertyInfo.DATA_TYPE_TEXT)
            
            return list(properties.values())
        except Exception as e:
            print(f"Error extracting RDF/XML properties: {e}")
            return []
    
    def _format_property_name(self, name: str) -> str:
        if not name:
            return ''
        return name.replace('_', ' ').replace('-', ' ').strip()


class RDFTurtleExtractionStrategy(PropertyExtractionStrategy):
    
    def extract_properties(self, content: str) -> List[PropertyInfo]:
        try:
            properties = {}
            
            sample_content = content[:10000] if len(content) > 10000 else content
            
            literal_pattern = r'([a-zA-Z0-9_-]+):([a-zA-Z0-9_-]+)\s+["\']([^"\']*)["\']'
            
            for match in re.finditer(literal_pattern, sample_content):
                namespace = match.group(1)
                predicate = match.group(2)
                value = match.group(3).strip()
                
                prop_name = self._format_property_name(predicate)
                
                if prop_name not in properties:
                    data_type = self._detect_type(value)
                    properties[prop_name] = PropertyInfo(prop_name, data_type)
            
            typed_literal_pattern = r'([a-zA-Z0-9_-]+):([a-zA-Z0-9_-]+)\s+"[^"]*"\^\^xsd:(\w+)'
            
            for match in re.finditer(typed_literal_pattern, sample_content):
                namespace = match.group(1)
                predicate = match.group(2)
                xsd_type = match.group(3).lower()
                
                prop_name = self._format_property_name(predicate)
                
                if prop_name not in properties:
                    if xsd_type in ['date', 'datetime', 'time']:
                        data_type = PropertyInfo.DATA_TYPE_DATE
                    elif xsd_type in ['integer', 'decimal', 'double', 'float']:
                        data_type = PropertyInfo.DATA_TYPE_NUMERIC
                    elif xsd_type == 'boolean':
                        data_type = PropertyInfo.DATA_TYPE_BOOLEAN
                    else:
                        data_type = PropertyInfo.DATA_TYPE_TEXT
                    
                    properties[prop_name] = PropertyInfo(prop_name, data_type)
            
            uri_pattern = r'([a-zA-Z0-9_-]+):([a-zA-Z0-9_-]+)\s+<[^>]+>'
            
            for match in re.finditer(uri_pattern, sample_content):
                namespace = match.group(1)
                predicate = match.group(2)
                
                prop_name = self._format_property_name(predicate)
                
                if prop_name not in properties:
                    properties[prop_name] = PropertyInfo(prop_name, PropertyInfo.DATA_TYPE_TEXT)
            
            return list(properties.values())
        except Exception as e:
            print(f"Error extracting Turtle properties: {e}")
            return []
    
    def _format_property_name(self, name: str) -> str:
        if not name:
            return ''
        return name.replace('_', ' ').replace('-', ' ').strip()
